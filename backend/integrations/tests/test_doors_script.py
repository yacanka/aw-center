"""Contract tests for standalone Excel-to-DXL generation (no DOORS runtime)."""

from io import BytesIO

from django.test import SimpleTestCase
from openpyxl import Workbook

from integrations.doors.serializers import ScriptGenerationSerializer
from integrations.doors.views import generate_dxl_script


class DoorsScriptGenerationTests(SimpleTestCase):
    """Verify emitted matching, write, and duplicate prevention contracts."""

    mappings = [
        {"excel": "Text", "doors": "Object Text", "search": False},
        {"excel": "Key", "doors": "Identifier", "search": True},
        {"excel": "Group", "doors": "Group", "search": True},
    ]

    def generate(self, mode="update", rows=None, mappings=None):
        """Render the real builder from a small in-memory workbook."""

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["Key", "Group", "Text"])
        for row in rows if rows is not None else [["REQ-1", "A", "Updated"]]:
            worksheet.append(row)
        source = BytesIO()
        workbook.save(source)
        workbook.close()
        return generate_dxl_script(source, mappings or self.mappings, mode)

    def test_all_unique_values_are_required_for_a_match(self):
        script = self.generate()["script"]
        self.assertIn(
            'awc_attribute_equals(candidate, "Identifier", awc_arr_1[row])', script
        )
        self.assertIn(
            '&& awc_attribute_equals(candidate, "Group", awc_arr_2[row])', script
        )
        self.assertNotIn('|| awc_attribute_equals', script)

    def test_update_visits_all_matches_and_keeps_keys_read_only(self):
        script = self.generate()["script"]
        self.assertIn("for o in entire(refModule) do", script)
        self.assertIn("if (!awc_matches(o, i)) continue", script)
        self.assertNotIn("break", script)
        self.assertIn('SetObjectAttribute(o, "Object Text", awc_arr_3[i])', script)
        self.assertNotIn('SetObjectAttribute(o, "Identifier",', script)
        self.assertNotIn('SetObjectAttribute(o, "Group",', script)
        self.assertIn("Object not found", script)

    def test_create_checks_duplicates_before_appending_and_writes_keys(self):
        script = self.generate("create")["script"]
        self.assertIn("Object already exists; row skipped", script)
        operation = script[script.index("for (i ="):]
        self.assertLess(
            operation.index("if (awc_found)"),
            operation.index("o = awc_append_object(refModule)"),
        )
        self.assertIn("if (null awc_tail) o = create(source)", script)
        self.assertIn("else o = create after awc_tail", script)
        self.assertIn("if (level(awc_candidate) == 1) awc_tail = awc_candidate", script)
        self.assertIn('SetObjectAttribute(o, "Identifier", awc_arr_1[i])', script)
        self.assertIn('SetObjectAttribute(o, "Group", awc_arr_2[i])', script)
        self.assertIn('SetObjectAttribute(o, "Object Text", awc_arr_3[i])', script)
        # Duplicate detection rescans the live module for each Excel row.
        self.assertLess(
            script.index("for (i ="), script.index("for o in entire(refModule)")
        )

    def test_empty_keys_warn_with_original_excel_row_numbers(self):
        for mode in ("update", "create"):
            with self.subTest(mode=mode):
                result = self.generate(mode, [[None, None, None], ["REQ-1", None, "Text"]])
                self.assertEqual(result["row_count"], 1)
                self.assertIn("int awc_excel_rows[] = {3}", result["script"])
                self.assertIn(
                    'if (awc_arr_1[i] == "" || awc_arr_2[i] == "")', result["script"]
                )
                self.assertIn("Empty Unique Attribute; row skipped", result["script"])

    def test_setter_is_self_contained_checked_and_does_not_save(self):
        script = self.generate()["script"]
        self.assertIn(
            "bool SetObjectAttribute(Object target, string attributeName, string value)",
            script,
        )
        self.assertIn("find(module(target), attributeName)", script)
        self.assertIn("canWrite(target.attributeName)", script)
        self.assertIn("target.attributeName = value", script)
        self.assertIn("string awc_write_error = lastError", script)
        self.assertIn("Changes have not been saved automatically", script)
        self.assertNotIn("#include", script)
        self.assertNotIn("save(", script)

    def test_preflight_validates_each_attribute_before_the_row_loop(self):
        script = self.generate()["script"]
        self.assertIn("if (!isEdit(refModule))", script)
        for name in ("Identifier", "Group", "Object Text"):
            self.assertLess(
                script.index(f'awc_require_attribute(refModule, "{name}")'),
                script.index("for (i ="),
            )

    def test_update_with_only_unique_mappings_has_no_writes(self):
        script = self.generate(mappings=self.mappings[1:])["script"]
        self.assertIn("No attribute updates were selected", script)
        self.assertNotIn("if (!SetObjectAttribute(o,", script)

    def test_serializer_defaults_to_update_and_rejects_duplicate_targets(self):
        serializer = ScriptGenerationSerializer(data={"json": self.mappings})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["mode"], "update")
        serializer = ScriptGenerationSerializer(data={
            "json": [
                {"excel": "Key", "doors": "Identifier", "search": True},
                {"excel": "Group", "doors": "identifier", "search": True},
            ]
        })
        self.assertFalse(serializer.is_valid())
