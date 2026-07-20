import json
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.base import ContentFile
from docx import Document

from dcc.document_snapshot import DccSnapshotError, build_snapshot
from dcc.document_preview import prepare_dcc_preview
from dcc.services.template_resolver import DccTemplateNotFoundError
from jobs.models import JobStatus
from jobs.services import create_job
from jobs.worker import claim_next_job, execute_claimed_job

from .base import JobTestCase


class DccSnapshotTests(JobTestCase):
    """Verify DCC snapshot boundary cases independently of JIRA transport."""

    def test_zero_subtasks_produces_a_valid_snapshot(self):
        """Parent tasks without panels no longer fail on an undefined last subtask."""

        issue = parent_issue([])
        snapshot = build_snapshot(fake_connector(), issue, "DCC-1", project_definition())

        self.assertEqual(snapshot["issue_key"], "DCC-1")
        self.assertNotIn("Responsible_AS", snapshot["placeholders"])

    def test_conflicting_explicit_responsible_values_are_rejected(self):
        """Conflicting compliance owners fail visibly instead of selecting one silently."""

        panels = [panel_issue("Owner A"), panel_issue("Owner B")]
        connector = fake_connector(panels)
        issue = parent_issue([SimpleNamespace(key="P-1"), SimpleNamespace(key="P-2")])

        with self.assertRaises(DccSnapshotError) as raised:
            build_snapshot(connector, issue, "DCC-1", project_definition())

        self.assertEqual(raised.exception.code, "DCC_RESPONSIBLE_CONFLICT")


class DccDocumentExecutorTests(JobTestCase):
    """Exercise real DOCX rendering, validation, and private artifact persistence."""

    def test_worker_renders_a_real_verified_docx(self):
        """The allowlisted worker produces a readable OOXML document without base64."""

        template_path = self.media_directory / "dcc-template.docx"
        create_template(template_path)
        upload = ContentFile(json.dumps(snapshot_contract()).encode(), name="dcc-DCC-1.json")
        job, _created = create_job(
            self.user, "dcc.create_document", "Create DCC", {"issue_key": "DCC-1"}, upload
        )

        with patch("dcc.document_job.get_project_definition", return_value=project_definition()):
            with patch("dcc.document_job.resolve_dcc_template_path", return_value=template_path):
                execute_claimed_job(claim_next_job("dcc-worker"))

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        with job.output_file.open("rb") as output:
            output_path = self.media_directory / "result.docx"
            output_path.write_bytes(output.read())
        self.assertTrue(zipfile.is_zipfile(output_path))
        self.assertIn("Change title", "\n".join(p.text for p in Document(output_path).paragraphs))

    def test_preview_dry_renders_exact_snapshot_and_reports_omissions(self):
        """Preflight proves template readiness and exposes only safe missing-field labels."""

        template_path = self.media_directory / "dcc-template.docx"
        create_template(template_path)
        snapshot = snapshot_contract()

        with patch("dcc.document_job.get_project_definition", return_value=project_definition()):
            with patch("dcc.document_job.resolve_dcc_template_path", return_value=template_path):
                summary = prepare_dcc_preview(snapshot)

        self.assertTrue(summary["template_ready"])
        self.assertEqual(summary["output_name"], "DCC-1.docx")
        self.assertIn("DCC form number", summary["missing_recommended_fields"])
        self.assertNotIn("Change title", str(summary))

    def test_missing_template_has_a_retryable_stable_failure(self):
        """Deployment template failures remain recoverable without exposing paths."""

        upload = ContentFile(json.dumps(snapshot_contract()).encode(), name="dcc-DCC-1.json")
        job, _created = create_job(
            self.user, "dcc.create_document", "Create DCC", {"issue_key": "DCC-1"}, upload
        )
        with patch("dcc.document_job.resolve_dcc_template_path") as resolver:
            resolver.side_effect = DccTemplateNotFoundError("private/path/template.docx")
            execute_claimed_job(claim_next_job("dcc-worker"))

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "DCC_TEMPLATE_UNAVAILABLE")
        self.assertTrue(job.retryable)
        self.assertNotIn("private/path", job.message)


def snapshot_contract():
    """Return a minimal versioned rendering snapshot."""

    return {
        "schema_version": 1,
        "issue_key": "DCC-1",
        "project_slug": "hys",
        "project_label": "HYS",
        "output_name": "DCC-1.docx",
        "panel_count": 0,
        "placeholders": {"Design_Change_Title": "Change title"},
    }


def parent_issue(subtasks):
    """Return a minimal parent issue accepted by the snapshot builder."""

    fields = SimpleNamespace(
        subtasks=subtasks, summary="Change title", customfield_45002="DCC-1",
        customfield_45000="ECD-1", customfield_45001="A", customfield_13716=None,
        updated="2026-06-30T00:00:00+00:00", customfield_34115=[],
    )
    return SimpleNamespace(fields=fields)


def panel_issue(responsible=""):
    """Return a minimal panel subtask issue."""

    fields = SimpleNamespace(
        status=SimpleNamespace(name="Done"), assignee=SimpleNamespace(displayName="Ada Lovelace"),
        updated="2026-06-30T00:00:00+00:00", customfield_45006=None,
        customfield_45007=None, customfield_45008="Assessment", customfield_45421=None,
        customfield_45004=SimpleNamespace(value="Minor-No Effect"),
        customfield_45005=responsible, comment=SimpleNamespace(comments=[]),
    )
    return SimpleNamespace(fields=fields)


def fake_connector(panels=None):
    """Return a connector double serving panel issues in order."""

    iterator = iter(panels or [])
    return SimpleNamespace(get_client=lambda: SimpleNamespace(issue=lambda _key: next(iterator)))


def project_definition():
    """Return the DCC-capable project fields required by snapshot and renderer."""

    return SimpleNamespace(slug="hys", display_name="HYS", jira_component="HYS")


def create_template(path):
    """Create a real DOCX template with one DocxTemplate placeholder."""

    document = Document()
    document.add_paragraph("{{ Design_Change_Title }}")
    document.save(path)
