"""Private policy loading and real DCC output regression tests."""

from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from docx import Document
from docxtpl import DocxTemplate

from integrations.jira.document_job import build_render_context, render_document, render_snapshot
from jobs.contracts import JobExecutionFailure
from projects.policies.gokbey import control_gokbey_dcc
from projects.policy_test_utils import private_dcc_policy


class GokbeyDccPolicyTests(SimpleTestCase):
    def setUp(self):
        self.policy_path = self.enterContext(private_dcc_policy())

    def test_existing_mandatory_responsible_is_not_duplicated(self):
        for current in ("Required Reviewer", "REQUIRED REVIEWER", ""):
            with self.subTest(current=current):
                result = control_gokbey_dcc({"Panels": [{
                    "Panel_Name": "Flight Panel Assessment", "Panel_AS_Name": current,
                }]})
                self.assertEqual(result["Panels"][0]["Panel_AS_Name"], "Required Reviewer")

    def test_all_three_assignments_are_merged_without_mutating_snapshot(self):
        panels = [
            {"Panel_Name": "Flight Panel Assessment", "Panel_AS_Name": "Jira Reviewer"},
            {"Panel_Name": "Human Factor Panel Assessment", "Panel_AS_Name": "Jira Reviewer"},
            {"Panel_Name": "Electrical Systems/E3 Panel Assessment", "Panel_AS_Name": "Jira Reviewer"},
            {"Panel_Name": "Safety Panel Assessment", "Panel_AS_Name": "Jira Reviewer"},
        ]
        snapshot = {"schema_version": 2, "project_slug": "gokbey", "placeholders": {"Panels": panels}}
        original = deepcopy(snapshot)
        context = build_render_context(snapshot)
        self.assertEqual([p["Panel_AS_Name"] for p in context["Panels"]], [
            "Required Reviewer, Jira Reviewer", "Human Reviewer, Jira Reviewer",
            "Electrical Reviewer, Jira Reviewer", "Jira Reviewer",
        ])
        self.assertEqual(snapshot, original)

    def test_real_docx_preserves_both_panel_contracts_and_xml_escaping(self):
        with TemporaryDirectory() as directory:
            template = Path(directory) / "template.docx"
            output = Path(directory) / "output.docx"
            document = Document()
            document.add_paragraph("{% for p in Panels %}{{ p.Panel_AS_Name }}{% endfor %}")
            document.add_paragraph("{% for p in panels %}{{ p.as_name }}{% endfor %}")
            document.save(template)
            render_document(DocxTemplate(template), {
                "schema_version": 2, "project_slug": "gokbey",
                "placeholders": {"Panels": [{"Panel_Name": "Flight Panel", "Panel_AS_Name": "Jira & Reviewer"}]},
            }, output)
            self.assertEqual([p.text for p in Document(output).paragraphs], [
                "Required Reviewer, Jira & Reviewer", "Required Reviewer, Jira & Reviewer",
            ])

    def test_explicit_lowercase_alias_keeps_existing_jira_value(self):
        snapshot = {"schema_version": 2, "project_slug": "gokbey", "placeholders": {
            "Panels": [{"Panel_Name": "Flight Panel", "Panel_AS_Name": "Jira Reviewer",
                        "as_name": "Jira Reviewer", "candidate_as_name": "Candidate Reviewer"}],
        }}
        original = deepcopy(snapshot)
        context = build_render_context(snapshot)
        self.assertEqual(context["Panels"][0]["Panel_AS_Name"], "Required Reviewer, Jira Reviewer")
        self.assertEqual(context["panels"][0]["as_name"], "Jira Reviewer")
        self.assertEqual(context["Panels"][0]["candidate_as_name"], "Candidate Reviewer")
        self.assertEqual(snapshot, original)

    def test_missing_invalid_or_incomplete_policy_cannot_produce_document_context(self):
        invalid = [
            "not json", "[]", '{"schema_version":2,"panel_responsibles":{}}',
            '{"schema_version":1,"panel_responsibles":{"flight":"Reviewer"}}',
            '{"schema_version":1,"schema_version":1,"panel_responsibles":{}}',
        ]
        for content in invalid:
            with self.subTest(content=content):
                self.policy_path.write_text(content, encoding="utf-8")
                with self.assertRaises(ImproperlyConfigured) as raised:
                    control_gokbey_dcc({"Panels": []})
                self.assertNotIn(str(self.policy_path), str(raised.exception))
                self.assertNotIn(content, str(raised.exception))
        self.policy_path.unlink()
        with self.assertRaises(ImproperlyConfigured):
            control_gokbey_dcc({"Panels": []})

    @override_settings(GOKBEY_DCC_POLICY_FILE="")
    def test_unconfigured_policy_fails_only_for_affected_project(self):
        with self.assertRaises(ImproperlyConfigured):
            control_gokbey_dcc({"Panels": []})
        snapshot = {"schema_version": 2, "project_slug": "hurkus", "placeholders": {"Panels": []}}
        self.assertEqual(build_render_context(snapshot)["Panels"], [])

    def test_external_absolute_path_is_required(self):
        for path in ("policy.json", str(Path(__file__).with_name("policy.json"))):
            with self.subTest(path=path), override_settings(GOKBEY_DCC_POLICY_FILE=path):
                with self.assertRaises(ImproperlyConfigured):
                    control_gokbey_dcc({"Panels": []})

    def test_oversized_policy_is_rejected(self):
        self.policy_path.write_bytes(b" " * (64 * 1024 + 1))
        with self.assertRaises(ImproperlyConfigured):
            control_gokbey_dcc({"Panels": []})

    def test_policy_edits_are_read_for_next_document(self):
        data = json.loads(self.policy_path.read_text())
        data["panel_responsibles"]["flight"] = "Replacement Reviewer"
        self.policy_path.write_text(json.dumps(data))
        result = control_gokbey_dcc({"Panels": [{"Panel_Name": "Flight Panel"}]})
        self.assertEqual(result["Panels"][0]["Panel_AS_Name"], "Replacement Reviewer")

    def test_group_or_world_access_is_rejected_on_posix(self):
        if os.name != "posix":
            self.skipTest("POSIX mode validation; Windows uses operator-verified ACLs.")
        self.policy_path.chmod(0o644)
        with self.assertRaises(ImproperlyConfigured):
            control_gokbey_dcc({"Panels": []})

    def test_invalid_names_are_rejected_without_echoing_values(self):
        original = json.loads(self.policy_path.read_text())
        for value in (None, [], "", "   ", "Bad\nName", "x" * 256):
            with self.subTest(value_type=type(value).__name__):
                data = deepcopy(original)
                data["panel_responsibles"]["flight"] = value
                self.policy_path.write_text(json.dumps(data))
                with self.assertRaises(ImproperlyConfigured):
                    control_gokbey_dcc({"Panels": []})

    @override_settings(GOKBEY_DCC_POLICY_FILE="")
    def test_missing_policy_returns_stable_job_error_and_no_docx(self):
        with TemporaryDirectory() as directory:
            template = Path(directory) / "gokbey_dcc_template.docx"
            output = Path(directory) / "result.docx"
            Document().save(template)
            with patch("integrations.jira.services.template_resolver.TEMPLATE_DIR", directory):
                with self.assertRaises(JobExecutionFailure) as raised:
                    render_snapshot({"schema_version": 2, "project_slug": "gokbey", "placeholders": {"Panels": []}}, output)
            self.assertEqual(raised.exception.code, "DCC_POLICY_UNAVAILABLE")
            self.assertFalse(output.exists())

    def test_symlink_loop_is_reported_as_sanitized_policy_error(self):
        if os.name != "posix":
            self.skipTest("Creating symlinks may require administrator rights on Windows.")
        loop = self.policy_path.with_name("loop.json")
        loop.symlink_to(loop)
        with override_settings(GOKBEY_DCC_POLICY_FILE=str(loop)):
            with self.assertRaises(ImproperlyConfigured) as raised:
                control_gokbey_dcc({"Panels": []})
        self.assertNotIn(str(loop), str(raised.exception))
