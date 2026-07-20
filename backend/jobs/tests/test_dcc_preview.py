"""Regression tests for preview-confirmed DCC document creation."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.utils import timezone

from dcc.document_snapshot import DccSnapshotError
from jobs.models import Job, JobStatus
from jobs.worker import claim_next_job

from .base import JobTestCase
from .test_dcc_jobs import snapshot_contract

PREVIEW_URL = "/dcc/jobs/create-document/preview/"


class DccPreviewApiTests(JobTestCase):
    """Verify private preview, explicit confirmation, and ownership boundaries."""

    def setUp(self):
        """Grant the scoped DCC creation permission to the preview owner."""

        super().setUp()
        self.permission = Permission.objects.get(codename="add_jira_dcc")
        self.user.user_permissions.add(self.permission)

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_preview_waits_for_confirmation_without_persisting_session(self, capture, prepare):
        """A dry-rendered snapshot is private and cannot be claimed by a worker."""

        configure_preview(capture, prepare)
        response = self.preview("dcc-preview-request-1", "sensitive-session")

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.status, JobStatus.AWAITING_CONFIRMATION)
        self.assertTrue(job.confirmation_expires_at)
        self.assertEqual(response.data["result_summary"]["panel_count"], 2)
        self.assertNotIn("JSESSIONID", job.parameters)
        with job.input_file.open("rb") as source:
            self.assertNotIn(b"sensitive-session", source.read())
        self.assertIsNone(claim_next_job("preview-worker"))

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_confirmation_queues_exact_snapshot_idempotently(self, capture, prepare):
        """Confirmation exposes the stored preview to workers without another JIRA read."""

        configure_preview(capture, prepare)
        preview = self.preview("dcc-preview-request-2")
        confirm_url = f"/dcc/jobs/create-document/{preview.data['id']}/confirm/"

        first = self.client.post(confirm_url, format="json")
        second = self.client.post(confirm_url, format="json")

        self.assertEqual(first.data["status"], JobStatus.QUEUED)
        self.assertEqual(second.data["status"], JobStatus.QUEUED)
        self.assertEqual(capture.call_count, 1)
        self.assertEqual(claim_next_job("confirmed-worker").id, Job.objects.get().id)

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_expired_preview_is_deleted_before_worker_exposure(self, capture, prepare):
        """Expired snapshots and their private artifacts cannot be confirmed."""

        configure_preview(capture, prepare)
        preview = self.preview("dcc-preview-request-3")
        job = Job.objects.get(pk=preview.data["id"])
        storage, artifact = job.input_file.storage, job.input_file.name
        job.confirmation_expires_at = timezone.now() - timedelta(seconds=1)
        job.save(update_fields=["confirmation_expires_at"])

        response = self.client.post(
            f"/dcc/jobs/create-document/{job.id}/confirm/", format="json"
        )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.data["code"], "DCC_PREVIEW_EXPIRED")
        self.assertFalse(Job.objects.filter(pk=job.id).exists())
        self.assertFalse(storage.exists(artifact))
        self.assertIsNone(claim_next_job("expired-worker"))

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_preview_replay_avoids_second_jira_read(self, capture, prepare):
        """Network retries return the same pending preview without recapturing JIRA."""

        configure_preview(capture, prepare)
        first = self.preview("dcc-preview-request-4")
        second = self.preview("dcc-preview-request-4")

        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(capture.call_count, 1)

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_preview_key_cannot_be_reused_for_another_issue(self, capture, prepare):
        """One idempotency key cannot silently select an unrelated JIRA source."""

        configure_preview(capture, prepare)
        self.preview("dcc-preview-request-conflict")
        response = self.preview("dcc-preview-request-conflict", issue="DCC-2")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(capture.call_count, 1)

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_other_user_cannot_confirm_owned_preview(self, capture, prepare):
        """A valid DCC permission never bypasses preview ownership."""

        configure_preview(capture, prepare)
        preview = self.preview("dcc-preview-request-5")
        self.other_user.user_permissions.add(self.permission)
        self.client.force_authenticate(self.other_user)

        response = self.client.post(
            f"/dcc/jobs/create-document/{preview.data['id']}/confirm/", format="json"
        )

        self.assertEqual(response.status_code, 404)

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_dry_render_failure_never_creates_a_job(self, capture, prepare):
        """Known template failures are reported before queue or persistence."""

        capture.return_value = snapshot_contract()
        prepare.side_effect = DccSnapshotError(
            "The configured DCC template is unavailable.", "DCC_TEMPLATE_UNAVAILABLE"
        )

        response = self.preview("dcc-preview-request-6")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "DCC_TEMPLATE_UNAVAILABLE")
        self.assertFalse(Job.objects.exists())

    def test_preview_requires_dcc_permission(self):
        """Authentication alone cannot capture a compliance source snapshot."""

        self.client.force_authenticate(self.other_user)
        response = self.preview("dcc-preview-request-7")

        self.assertEqual(response.status_code, 403)

    def preview(self, key, session="temporary", issue="DCC-1"):
        """Submit one deterministic DCC preview request."""

        return self.client.post(
            PREVIEW_URL, {"JSESSIONID": session, "url": issue}, format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )


class DccPreviewCleanupTests(JobTestCase):
    """Verify abandoned compliance snapshots follow their short retention boundary."""

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_cleanup_removes_expired_unconfirmed_snapshot(self, capture, prepare):
        """Scheduled cleanup deletes both the preview row and private bytes."""

        self.user.user_permissions.add(Permission.objects.get(codename="add_jira_dcc"))
        configure_preview(capture, prepare)
        response = self.client.post(
            PREVIEW_URL, {"JSESSIONID": "sid", "url": "DCC-1"}, format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-cleanup-request",
        )
        job = Job.objects.get(pk=response.data["id"])
        storage, artifact = job.input_file.storage, job.input_file.name
        job.confirmation_expires_at = timezone.now() - timedelta(seconds=1)
        job.save(update_fields=["confirmation_expires_at"])

        call_command("cleanup_jobs", days=30)

        self.assertFalse(Job.objects.filter(pk=job.id).exists())
        self.assertFalse(storage.exists(artifact))


def configure_preview(capture, prepare):
    """Configure safe snapshot and content-free preview doubles."""

    capture.return_value = snapshot_contract()
    prepare.return_value = {
        "type": "dcc_preview", "issue_key": "DCC-1", "project": "HYS",
        "output_name": "DCC-1.docx", "panel_count": 2, "template_ready": True,
        "source_updated_at": "2026-07-20", "missing_recommended_fields": [],
        "warning_count": 0,
    }
