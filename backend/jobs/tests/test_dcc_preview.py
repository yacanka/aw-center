"""Regression tests for role-scoped preview-confirmed DCC document jobs."""

from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.utils import timezone

from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from jobs.worker import claim_next_job
from orgs.models import Project, ProjectRoleAssignment

from .test_dcc_jobs import snapshot_contract

PREVIEW_URL = "/api/dcc/jobs/create-document/preview/"


class DccPreviewApiTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.get(slug="hys")
        self.assignment = ProjectRoleAssignment.objects.create(
            user=self.user,
            project=self.project,
            domain=ProjectRoleAssignment.Domain.DCC,
            role=ProjectRoleAssignment.Role.OPERATOR,
        )
        self.capture_patcher = patch("dcc.job_views.capture_dcc_snapshot")
        self.prepare_patcher = patch("dcc.job_views.prepare_dcc_preview")
        self.connector_patcher = patch("dcc.job_views.jira_connector_for")
        self.capture = self.capture_patcher.start()
        self.prepare = self.prepare_patcher.start()
        self.connector_for = self.connector_patcher.start()
        self.addCleanup(self.capture_patcher.stop)
        self.addCleanup(self.prepare_patcher.stop)
        self.addCleanup(self.connector_patcher.stop)
        self.capture.return_value = snapshot_contract([self.project.pk])
        self.prepare.return_value = preview_summary()

    def preview(self, key, issue="DCC-1", payload=None):
        return self.client.post(
            PREVIEW_URL,
            payload or {"url": issue},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_preview_is_private_awaiting_confirmation_and_credential_free(self):
        response = self.preview("dcc-preview-request-1")

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.status, JobStatus.AWAITING_CONFIRMATION)
        self.assertEqual(job.parameters["project_ids"], [self.project.pk])
        self.assertNotIn("JSESSIONID", str(job.parameters))
        with job.input_file.open("rb") as source:
            self.assertNotIn(b"JSESSIONID", source.read())
        self.assertIsNone(claim_next_job("preview-worker"))
        self.capture.assert_called_once_with(
            self.connector_for.return_value,
            "DCC-1",
            self.user,
        )

    def test_confirmation_rechecks_operator_role(self):
        preview = self.preview("dcc-preview-request-2")
        url = f"/api/dcc/jobs/create-document/{preview.data['id']}/confirm/"
        self.assignment.role = ProjectRoleAssignment.Role.VIEWER
        self.assignment.save()

        blocked = self.client.post(url, {}, format="json")
        self.assignment.role = ProjectRoleAssignment.Role.OPERATOR
        self.assignment.save()
        confirmed = self.client.post(url, {}, format="json")

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(confirmed.data["status"], JobStatus.QUEUED)

    def test_preview_idempotency_replays_without_second_jira_read(self):
        first = self.preview("dcc-preview-request-3")
        replay = self.preview("dcc-preview-request-3")

        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(self.capture.call_count, 1)

    def test_legacy_session_payload_is_rejected(self):
        response = self.preview(
            "dcc-preview-request-4",
            payload={"url": "DCC-1", "JSESSIONID": "never-store"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "JIRA_SESSION_CANONICAL_REQUIRED")
        self.capture.assert_not_called()
        self.assertFalse(Job.objects.exists())

    def test_other_user_cannot_confirm_owned_preview(self):
        preview = self.preview("dcc-preview-request-5")
        ProjectRoleAssignment.objects.create(
            user=self.other_user,
            project=self.project,
            domain=ProjectRoleAssignment.Domain.DCC,
            role=ProjectRoleAssignment.Role.OPERATOR,
        )
        self.client.force_authenticate(self.other_user)

        response = self.client.post(
            f"/api/dcc/jobs/create-document/{preview.data['id']}/confirm/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_cleanup_removes_expired_unconfirmed_snapshot(self):
        response = self.preview("dcc-cleanup-request")
        job = Job.objects.get(pk=response.data["id"])
        storage, artifact = job.input_file.storage, job.input_file.name
        job.confirmation_expires_at = timezone.now() - timedelta(seconds=1)
        job.save(update_fields=["confirmation_expires_at"])

        call_command("cleanup_jobs", days=30)

        self.assertFalse(Job.objects.filter(pk=job.id).exists())
        self.assertFalse(storage.exists(artifact))


def preview_summary():
    return {
        "type": "dcc_preview",
        "issue_key": "DCC-1",
        "project": "HYS",
        "output_name": "DCC-1.docx",
        "panel_count": 2,
        "template_ready": True,
        "source_updated_at": "2026-07-20",
        "missing_recommended_fields": [],
        "warning_count": 0,
    }
