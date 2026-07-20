"""Regression tests for persistent reverse CompDoc-to-DCC traceability."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.utils import timezone

from dcc.compdoc_bridge import attach_compliance_documents
from dcc.models import DccCompdocTrace
from jobs.models import Job, JobStatus
from jobs.services import set_job_state
from jobs.tests.base import JobTestCase
from projects.ozgur.models import CompDoc

PREVIEW_URL = "/dcc/jobs/create-document/preview/"
TRACE_URL = "/dcc/compdoc-traceability/"


class CompdocTraceabilityTests(JobTestCase):
    """Verify confirmation audit persistence, permissions, retries, and stale detection."""

    def setUp(self):
        super().setUp()
        self.document = CompDoc.objects.create(
            name="Traceable Manual", cover_page_no="TRACE-1", tech_doc_no="TD-1",
            status_flow=[{"status": "authority_review"}],
        )
        self.add_permission = permission("dcc", "add_jira_dcc")
        self.dcc_view_permission = permission("dcc", "view_jira_dcc")
        self.compdoc_view_permission = permission("ozgur", "view_compdoc")
        self.user.user_permissions.add(
            self.add_permission, self.dcc_view_permission, self.compdoc_view_permission
        )

    def test_confirmation_persists_exact_trace_once(self):
        """Confirmation atomically writes one source-version and fingerprint audit row."""

        preview, confirmation = self.confirm_trace()
        replay = self.client.post(confirm_url(preview), format="json")
        trace = DccCompdocTrace.objects.get()
        job = Job.objects.get(pk=preview.data["id"])

        self.assertEqual(confirmation.data["status"], JobStatus.QUEUED)
        self.assertEqual(replay.data["status"], JobStatus.QUEUED)
        self.assertEqual(DccCompdocTrace.objects.count(), 1)
        self.assertEqual(trace.job_input_sha256, job.input_sha256)
        self.assertEqual(trace.source_history_id, self.document.history.first().history_id)
        self.assertEqual(len(trace.snapshot_fingerprint), 64)

    def test_preview_and_expiry_never_create_false_usage(self):
        """Only confirmation, never preview or expiry, creates reverse provenance."""

        preview = self.create_preview()
        job = Job.objects.get(pk=preview.data["id"])
        self.assertFalse(DccCompdocTrace.objects.exists())
        job.confirmation_expires_at = timezone.now() - timedelta(seconds=1)
        job.save(update_fields=["confirmation_expires_at"])

        response = self.client.post(confirm_url(preview), format="json")

        self.assertEqual(response.status_code, 410)
        self.assertFalse(DccCompdocTrace.objects.exists())

    def test_history_reports_current_then_stale_source_version(self):
        """A later CompDoc edit makes the confirmed source visibly stale."""

        preview, _confirmation = self.confirm_trace()
        current = self.trace_response()
        self.document.notes = "Metadata outside the DCC register"
        self.document.save(update_fields=["notes"])
        metadata_only = self.trace_response()
        self.document.name = "Updated Manual"
        self.document.save()
        stale = self.trace_response()

        self.assertTrue(current.data["results"][0]["is_current_version"])
        comparison = metadata_only.data["results"][0]["source_change"]
        self.assertEqual(comparison["comparison_status"], "unchanged")
        self.assertFalse(stale.data["results"][0]["is_current_version"])
        source_change = stale.data["results"][0]["source_change"]
        self.assertEqual(source_change["comparison_status"], "changed")
        self.assertEqual(source_change["changed_fields"][0]["code"], "name")
        self.assertEqual(current.data["results"][0]["job_id"], preview.data["id"])
        self.assertTrue(current.data["results"][0]["can_open_job"])

    def test_reverse_history_resolves_latest_retry_by_input_sha(self):
        """Retries remain one provenance chain while exposing the newest retained attempt."""

        preview, _confirmation = self.confirm_trace()
        job = Job.objects.get(pk=preview.data["id"])
        set_job_state(job, JobStatus.FAILED, 10, "Retryable failure.", "DCC_RENDER_FAILED")
        retry = self.client.post(f"/jobs/{job.id}/retry/", format="json")

        response = self.trace_response()

        self.assertEqual(retry.status_code, 201)
        self.assertEqual(response.data["results"][0]["job_attempt"], 2)
        self.assertEqual(response.data["results"][0]["job_id"], retry.data["id"])
        self.assertEqual(response.data["results"][0]["job_status"], JobStatus.QUEUED)

    def test_trace_survives_job_retention_as_archived_provenance(self):
        """Deleting retained job files does not erase the compliance audit record."""

        preview, _confirmation = self.confirm_trace()
        Job.objects.get(pk=preview.data["id"]).delete()

        response = self.trace_response()

        self.assertEqual(DccCompdocTrace.objects.count(), 1)
        self.assertEqual(response.data["results"][0]["job_status"], "archived")
        self.assertIsNone(response.data["results"][0]["job_id"])

    def test_cross_owner_history_requires_both_read_permissions(self):
        """Project-only or DCC-only users cannot inspect reverse traceability."""

        self.confirm_trace()
        self.other_user.user_permissions.add(self.compdoc_view_permission)
        self.client.force_authenticate(self.other_user)
        missing_dcc = self.trace_response()
        self.other_user.user_permissions.add(self.dcc_view_permission)
        self.other_user = type(self.other_user).objects.get(pk=self.other_user.pk)
        self.client.force_authenticate(self.other_user)
        allowed = self.trace_response()

        self.assertEqual(missing_dcc.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertFalse(allowed.data["results"][0]["can_open_job"])
        self.assertIsNone(allowed.data["results"][0]["job_id"])

    def confirm_trace(self):
        """Create and confirm one real private CompDoc-backed DCC preview."""

        preview = self.create_preview()
        return preview, self.client.post(confirm_url(preview), format="json")

    def create_preview(self):
        """Create one real private CompDoc-backed preview without confirming it."""

        captured = attach_compliance_documents(
            snapshot(), self.user, "ozgur", [str(self.document.pk)]
        )
        with (
            patch("dcc.job_views.capture_dcc_snapshot", return_value=captured),
            patch("dcc.job_views.prepare_dcc_preview", return_value=preview_summary()),
        ):
            preview = self.client.post(
                PREVIEW_URL, preview_payload(self.document.pk), format="json",
                HTTP_IDEMPOTENCY_KEY=f"trace-{self.document.pk}",
            )
        return preview

    def trace_response(self):
        """Request the current document's reverse DCC history."""

        return self.client.get(
            TRACE_URL, {"project": "ozgur", "compdoc_id": str(self.document.pk)}
        )


def permission(app_label, codename):
    """Return an unambiguous permission fixture."""

    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def confirm_url(preview):
    """Return the confirmation endpoint for a preview response."""

    return f"/dcc/jobs/create-document/{preview.data['id']}/confirm/"


def snapshot():
    """Return a minimal Ozgur DCC rendering snapshot."""

    return {
        "schema_version": 1, "issue_key": "DCC-TRACE-1", "project_slug": "ozgur",
        "project_label": "Ozgur", "output_name": "trace.docx", "panel_count": 0,
        "placeholders": {"Design_Change_Title": "Trace"},
    }


def preview_payload(document_id):
    """Return a CompDoc-backed DCC preview request."""

    return {
        "JSESSIONID": "temporary", "url": "DCC-TRACE-1", "compdoc_project": "ozgur",
        "compdoc_ids": [str(document_id)],
    }


def preview_summary():
    """Return safe confirmation summary metadata."""

    return {
        "type": "dcc_preview", "issue_key": "DCC-TRACE-1", "project": "Ozgur",
        "output_name": "trace.docx", "panel_count": 0, "template_ready": True,
    }
