"""API tests for audited DCC readiness acknowledgement."""

from unittest.mock import patch

from django.contrib.auth.models import Permission

from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from jobs.tests.test_dcc_jobs import snapshot_contract

PREVIEW_URL = "/dcc/jobs/create-document/preview/"
WARNING_CODE = "DCC_PANEL_COVERAGE"


class DccReadinessConfirmationTests(JobTestCase):
    """Verify warning acknowledgement is required and audited atomically."""

    def setUp(self):
        """Grant DCC creation to the preview owner."""

        super().setUp()
        self.user.user_permissions.add(Permission.objects.get(codename="add_jira_dcc"))

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_confirmation_requires_and_audits_exact_warning_codes(self, capture, prepare):
        """An unacknowledged warning cannot silently enter the worker queue."""

        capture.return_value = snapshot_contract()
        prepare.return_value = warning_summary()
        preview = self.client.post(
            PREVIEW_URL, {"JSESSIONID": "temporary", "url": "DCC-1"}, format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-readiness-confirmation",
        )
        confirm_url = f"/dcc/jobs/create-document/{preview.data['id']}/confirm/"

        blocked = self.client.post(confirm_url, {}, format="json")
        self.assertEqual(Job.objects.get(pk=preview.data["id"]).status, JobStatus.AWAITING_CONFIRMATION)
        confirmed = self.client.post(
            confirm_url, {"acknowledged_warning_codes": [WARNING_CODE]}, format="json"
        )
        replay = self.client.post(confirm_url, {}, format="json")

        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data["code"], "DCC_READINESS_ACK_REQUIRED")
        self.assertEqual(confirmed.data["status"], JobStatus.QUEUED)
        self.assertEqual(replay.data["status"], JobStatus.QUEUED)
        job = Job.objects.get(pk=preview.data["id"])
        event = job.events.get(code="DCC_READINESS_ACKNOWLEDGED")
        self.assertEqual(event.details["warning_codes"], [WARNING_CODE])


def warning_summary():
    """Return a safe preview summary with one required acknowledgement."""

    return {
        "type": "dcc_preview", "issue_key": "DCC-1", "project": "HYS",
        "output_name": "DCC-1.docx", "panel_count": 0, "template_ready": True,
        "readiness_score": 80, "readiness_level": "review",
        "readiness_checks": [], "readiness_warning_codes": [WARNING_CODE],
        "requires_readiness_acknowledgement": True, "warning_count": 1,
    }
