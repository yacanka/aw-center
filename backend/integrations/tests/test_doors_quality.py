"""ATA/panel quality analysis and artifact adapter regression coverage."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from integrations.doors.quality import analyze_module, chapters_from, discover_attribute
from integrations.doors.worker_tasks import check_module_quality, WorkerTaskPayloadError
from jobs.contracts import JobCancelled, JobLeaseLost


def snapshot(values, columns=None, **flags):
    names = columns or ["ATA Chapter", "Panel Name"]
    return {
        "columns": names,
        "results": [
            {"absolute_number": index, "identifier": f"REQ-{index}",
             "attributes": dict(zip(names, pair))}
            for index, pair in enumerate(values, start=1)
        ],
        "truncated": False, "attributes_truncated": False, **flags,
    }


class DoorsQualityTests(SimpleTestCase):
    def analyze(self, values, **kwargs):
        return analyze_module(snapshot(values, **kwargs), Mock())

    def test_conflicts_include_raw_evidence_and_solution(self):
        result = self.analyze([("ATA 27-10-00", "Flight Controls"), ("27", "Hydraulics")])
        self.assertEqual(result["outcome"], "review_required")
        self.assertEqual(result["summary"]["conflicting_chapters"], 1)
        finding = result["findings"][0]
        self.assertEqual(finding["chapter"], "27")
        self.assertEqual(finding["panels"], ["flight controls", "hydraulics"])
        self.assertEqual([item["absolute_number"] for item in finding["evidence"]], [1, 2])
        self.assertEqual(finding["evidence"][0]["ata_value"], "ATA 27-10-00")
        self.assertIn("correct", finding["suggestion"])

    def test_small_value_differences_do_not_create_conflicts(self):
        result = self.analyze([("27", " Flight   Controls "), ("27-10", "flight controls")])
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(result["summary"]["checked_objects"], 2)

    def test_panel_typos_are_not_silently_merged(self):
        result = self.analyze([("27", "Panel A"), ("27", "Panel B")])
        self.assertEqual(result["summary"]["conflicting_chapters"], 1)

    def test_missing_unparseable_and_unpaired_values_require_review(self):
        result = self.analyze([("27", ""), ("unknown 27", "A"), ("27;28", "A;B"), ("", "")])
        self.assertFalse(result["complete"])
        self.assertEqual(result["summary"]["unresolved_objects"], 3)
        self.assertEqual(result["summary"]["unassigned_objects"], 1)
        self.assertEqual(result["summary"]["chapters"], 0)
        self.assertEqual([item["code"] for item in result["findings"]], ["missing_value", "invalid_value", "ambiguous_assignment"])

    def test_single_chapter_multiple_panels_is_a_conflict(self):
        result = self.analyze([("27", "A; B")])
        self.assertEqual(result["summary"]["conflicting_chapters"], 1)

    def test_multiple_chapters_may_share_a_panel(self):
        result = self.analyze([("27; 28", "A")])
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(result["summary"]["chapters"], 2)

    def test_incomplete_exports_and_empty_modules_never_pass(self):
        for flags in ({"truncated": True}, {"attributes_truncated": True}):
            with self.subTest(flags=flags):
                self.assertEqual(self.analyze([("27", "A")], **flags)["outcome"], "incomplete")
        self.assertEqual(self.analyze([])["outcome"], "incomplete")
        self.assertEqual(self.analyze([("", "")])["outcome"], "incomplete")

    def test_missing_and_ambiguous_attributes_do_not_guess(self):
        for columns in (["Object Text", "Panel"], ["ATA", "ATA Chapter", "Panel"]):
            result = analyze_module(snapshot([], columns=columns), Mock())
            self.assertIsNone(result["attributes"]["ata"]["name"])
            self.assertEqual(result["outcome"], "incomplete")

    def test_heuristic_names_are_reported_for_confirmation(self):
        result = self.analyze([("27", "A")], columns=["ATA Chaper", "Responsible Panel"])
        self.assertEqual(result["outcome"], "review_required")
        self.assertTrue(result["complete"])
        self.assertEqual(result["attributes"]["ata"]["method"], "heuristic")
        self.assertEqual(result["attributes"]["panel"]["method"], "heuristic")
        self.assertEqual(len(result["warnings"]), 2)

    def test_exact_names_take_precedence_and_qualified_candidates_remain_ambiguous(self):
        self.assertEqual(discover_attribute(["ATA", "Old ATA"], "ata")["name"], "ATA")
        self.assertIsNone(discover_attribute(["Old ATA", "New ATA"], "ata")["name"])
        self.assertIsNone(discover_attribute(["Database", "Panelist"], "ata")["name"])

    def test_ata_formats_are_conservative(self):
        for value in ("127", "27-28 text", "27/invalid", "27 to 29", "270000"):
            self.assertEqual(chapters_from(value), set())
        self.assertEqual(chapters_from("ATA 7; 27-10-00; 28.00"), {"07", "27", "28"})

    def test_report_is_bounded_without_hiding_conflict_counts(self):
        result = self.analyze([("invalid", "A")] * 250 + [("27", "A"), ("27", "B")])
        self.assertEqual(result["summary"]["finding_count"], 251)
        self.assertEqual(result["summary"]["omitted_findings"], 51)
        self.assertEqual(len(result["findings"]), 200)
        self.assertEqual(result["findings"][0]["code"], "multiple_panels")

    def test_progress_is_ordered_and_can_abort_the_analysis(self):
        progress = Mock()
        analyze_module(snapshot([("27", "A")] * 1001), progress)
        values = [call.args[0] for call in progress.call_args_list]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[0], 45)
        self.assertEqual(values[-1], 95)
        for error in (JobCancelled, JobLeaseLost):
            with self.assertRaises(error):
                analyze_module(snapshot([("27", "A")]), Mock(side_effect=error()))

    @patch("integrations.doors.worker_tasks.execute_with_client")
    def test_worker_reads_only_and_writes_a_versioned_result(self, execute):
        client, progress = Mock(), Mock()
        client.export_module.return_value = snapshot([("27", "A")])
        execute.side_effect = lambda operation: operation(client)
        with tempfile.TemporaryDirectory() as temporary:
            input_path, output_path = Path(temporary) / "input.json", Path(temporary) / "result.json"
            input_path.write_text(json.dumps({"module_path": "/Project/Module"}))
            metadata = check_module_quality(input_path, output_path, progress=progress)
            result = json.loads(output_path.read_text())
        client.export_module.assert_called_once_with("/Project/Module", 10000)
        self.assertEqual(len(client.mock_calls), 1)
        self.assertEqual(progress.call_args_list[0].args[0], 10)
        self.assertEqual(result["module_path"], "/Project/Module")
        self.assertEqual(result["operation_result"]["operation"], "check_module_quality")
        self.assertTrue(metadata["sha256_required"])

    @patch("integrations.doors.worker_tasks.execute_with_client")
    def test_worker_rejects_unknown_inputs_before_accessing_doors(self, execute):
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "input.json"
            input_path.write_text(json.dumps({"module_path": "/Project/Module", "script": "unexpected"}))
            with self.assertRaises(WorkerTaskPayloadError):
                check_module_quality(input_path, Path(temporary) / "out.json")
        execute.assert_not_called()
