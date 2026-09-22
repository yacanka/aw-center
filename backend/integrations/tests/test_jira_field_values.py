"""Schema/value regressions without an external JIRA connection."""

from types import SimpleNamespace
from unittest import TestCase

from rest_framework.exceptions import ValidationError

from integrations.jira.contracts import validate_extra_fields
from integrations.jira.create_contract import inspect_create_contract, value_supported
from integrations.jira.field_values import encode_value
from dcc.subtask_contracts import sanitize_subtask_fields, validate_item_field_contract


def metadata(kind, **kwargs):
    return {"id": "customfield_123", "name": "Review field", "schema": {"type": kind}, **kwargs}


class JiraFieldValuesTests(TestCase):
    def test_reference_shapes_and_arrays(self):
        cases = [
            ("option", "Review", {"value": "Review"}),
            ("user", "reviewer", {"name": "reviewer"}),
            ("user", {"accountId": "account-1"}, {"accountId": "account-1"}),
            ("component", {"id": 12}, {"id": "12"}),
            ("version", {"name": "Release"}, {"name": "Release"}),
            ("group", "reviewers", {"name": "reviewers"}),
        ]
        for kind, value, expected in cases:
            with self.subTest(kind=kind, value=value):
                self.assertEqual(encode_value(value, metadata(kind)), expected)
                field = metadata("array")
                field["schema"]["items"] = kind
                self.assertEqual(encode_value([value], field), [expected])
                self.assertFalse(value_supported(value, field))

    def test_numbers_booleans_dates_and_zero(self):
        for kind, value, expected in [
            ("number", "2.5", 2.5), ("integer", "0", 0),
            ("boolean", "false", False), ("boolean", False, False),
            ("date", "2026-09-22", "2026-09-22"),
            ("datetime", "2026-09-22T10:30:00+03:00", "2026-09-22T10:30:00.000+0300"),
        ]:
            with self.subTest(kind=kind):
                self.assertEqual(encode_value(value, metadata(kind)), expected)
        for kind, value in [
            ("integer", 1.5), ("number", True), ("number", "NaN"),
            ("number", float("inf")), ("date", "2026-02-30"),
            ("datetime", "2026-09-22T10:30:00"), ("string", {"id": "12"}),
            ("object", "text"), ("option", {"unrecognized": "text"}),
        ]:
            with self.subTest(kind=kind, value=value):
                self.assertFalse(value_supported(value, metadata(kind)))

    def test_options_resolve_to_ids_and_reject_ambiguity(self):
        field = metadata("option", allowedValues=[
            {"id": "10", "value": "Review"}, {"id": "20", "value": "Review"},
            {"id": "30", "value": "Disabled", "disabled": True},
        ])
        for value in ("10", {"id": "10", "value": "Old name"}):
            self.assertEqual(encode_value(value, field), {"id": "10"})
        for value in ("Review", "30", "Missing"):
            self.assertFalse(value_supported(value, field))

    def test_cascade_public_and_live_metadata_accept_same_reference(self):
        field = metadata("option", allowedValues=[{
            "id": "10", "value": "Parent", "children": [{"id": "11", "value": "Child"}],
        }])
        field["schema"]["custom"] = "com.atlassian.jira.plugin.system.customfieldtypes:cascadingselect"
        value = {"id": "10", "child": {"id": "11"}}
        public = sanitize_subtask_fields([field])[0]
        self.assertTrue(value_supported(value, public))
        explicit = {**field, "schema": {"type": "option-with-child"}}
        self.assertEqual(encode_value(value, explicit), value)
        self.assertEqual(len(sanitize_subtask_fields([explicit])), 1)
        self.assertEqual(encode_value(value, field), value)
        self.assertFalse(value_supported({"id": "10", "child": {"id": "99"}}, field))

    def test_serializer_keeps_bounded_references_and_rejects_arbitrary_objects(self):
        for value in ({"id": "10"}, {"name": "reviewer"}, False, [{"id": "10"}]):
            self.assertEqual(validate_extra_fields({"customfield_123": value})["customfield_123"], value)
        for value in ({"self": "private"}, {"child": {"id": "10"}}, {"id": {}}, float("nan")):
            with self.assertRaises(ValidationError):
                validate_extra_fields({"customfield_123": value})

    def test_unknown_required_fields_block_and_errors_identify_column(self):
        fields = sanitize_subtask_fields([metadata("object", required=True)])
        self.assertEqual(len(fields), 1)
        with self.assertRaises(ValidationError):
            validate_item_field_contract([{"fields": {}}], fields)
        with self.assertRaisesRegex(ValidationError, "row 1: Review field"):
            validate_item_field_contract([{"fields": {"customfield_123": "bad"}}], [metadata("number")])

    def test_optional_draft_values_are_preflight_validated(self):
        fields = [{"id": key, "schema": {"type": "string"}} for key in ("summary", "description", "labels")]
        fields.append(metadata("integer"))
        client = SimpleNamespace(get_create_fields=lambda *args: fields)
        result, _ = inspect_create_contract(SimpleNamespace(project_key="TEST", extra_fields={"customfield_123": 1.5}), client)
        self.assertFalse(result["ready"])
        self.assertEqual(result["invalid_fields"][0]["id"], "customfield_123")

    def test_array_numbers_are_encoded_and_assignee_uses_live_reference(self):
        from dcc.subtask_executor import prepare_extra_fields

        field = metadata("array")
        field["schema"]["items"] = "number"
        self.assertEqual(encode_value(["0", "2.5"], field), [0, 2.5])
        assignee = {"id": "assignee", "name": "Assignee", "schema": {"type": "user"},
                    "allowedValues": [{"accountId": "account-1", "displayName": "Reviewer"}]}
        client = SimpleNamespace(get_subtask_fields=lambda: [assignee, field])
        encoded = prepare_extra_fields(client, {"items": [{"summary": "Review",
            "assignee": "account-1", "fields": {"customfield_123": ["0", "2.5"]}}]})
        self.assertEqual(encoded, [{"assignee": {"accountId": "account-1"}, "customfield_123": [0, 2.5]}])
