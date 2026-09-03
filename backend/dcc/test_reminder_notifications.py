"""Durability and credential-boundary tests for Watcher reminder mail."""

from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment

from .models import DccRecord, DccReminderDelivery
from .reminder_notifications import claim_dcc_reminders, deliver_dcc_reminder


@override_settings(JIRA_ENABLED=True)
class DccReminderTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user("reminder-owner", password="pass")
        self.project = Project.objects.get(slug="hys")
        ProjectRoleAssignment.objects.create(
            user=self.user,
            project=self.project,
            domain=ProjectRoleAssignment.Domain.DCC,
            role=ProjectRoleAssignment.Role.OPERATOR,
        )
        self.record = DccRecord.objects.create(
            issue="CHN-42",
            title="ECD title",
            owner=self.user,
        )
        self.record.projects.add(self.project)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("dcc.reminder_service.build_reminder_snapshot")
    def test_api_materializes_idempotent_outbox_without_credentials(self, build_snapshot):
        build_snapshot.return_value = reminder_snapshot(self.record)
        payload = {"version": 1, "ccb_no": 12, "due_date": "2026-09-10"}

        first = self.client.post(
            f"/api/dcc/records/{self.record.id}/reminders/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-reminder-001",
        )
        replay = self.client.post(
            f"/api/dcc/records/{self.record.id}/reminders/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-reminder-001",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(DccReminderDelivery.objects.count(), 1)
        delivery = DccReminderDelivery.objects.get()
        self.assertNotIn("JSESSIONID", str(delivery.context))
        self.assertNotIn("recipient@example.test", str(first.data))

    @patch("dcc.reminder_service.build_reminder_snapshot")
    def test_second_distinct_request_is_rate_limited(self, build_snapshot):
        build_snapshot.return_value = reminder_snapshot(self.record)
        payload = {"version": 1, "ccb_no": 12, "due_date": "2026-09-10"}
        self.client.post(
            f"/api/dcc/records/{self.record.id}/reminders/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-reminder-002",
        )

        response = self.client.post(
            f"/api/dcc/records/{self.record.id}/reminders/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-reminder-003",
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "DCC_REMINDER_COOLDOWN")

    def test_legacy_session_payload_is_rejected(self):
        response = self.client.post(
            f"/api/dcc/records/{self.record.id}/reminders/",
            {
                "version": 1,
                "ccb_no": 12,
                "due_date": "2026-09-10",
                "JSESSIONID": "must-not-be-accepted",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-reminder-004",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "JIRA_SESSION_CANONICAL_REQUIRED")

    @patch("dcc.reminder_service.build_reminder_snapshot")
    def test_inactive_record_is_rejected_before_jira_access(self, build_snapshot):
        self.record.active = False
        self.record.save(update_fields=("active",))

        response = self.client.post(
            f"/api/dcc/records/{self.record.id}/reminders/",
            {"version": 1, "ccb_no": 12, "due_date": "2026-09-10"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-reminder-inactive-001",
        )

        self.assertEqual(response.status_code, 400)
        build_snapshot.assert_not_called()

    @patch("dcc.reminder_service.build_reminder_snapshot")
    def test_stale_record_version_is_rejected_before_jira_access(self, build_snapshot):
        self.record.version = 2
        self.record.save(update_fields=("version",))

        response = self.client.post(
            f"/api/dcc/records/{self.record.id}/reminders/",
            {"version": 1, "ccb_no": 12, "due_date": "2026-09-10"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-reminder-stale-001",
        )

        self.assertEqual(response.status_code, 400)
        build_snapshot.assert_not_called()

    @patch("dcc.reminder_service.build_reminder_snapshot")
    def test_unassigned_user_cannot_discover_or_queue_record(self, build_snapshot):
        from django.contrib.auth import get_user_model

        outsider = get_user_model().objects.create_user("reminder-outsider", password="pass")
        self.client.force_authenticate(outsider)

        response = self.client.post(
            f"/api/dcc/records/{self.record.id}/reminders/",
            {"version": 1, "ccb_no": 12, "due_date": "2026-09-10"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-reminder-outsider-001",
        )

        self.assertEqual(response.status_code, 404)
        build_snapshot.assert_not_called()

    @override_settings(
        AWCENTER_MAIL_TRANSPORT="django",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_notification_worker_delivers_claimed_reminder_with_stable_message_id(self):
        delivery = DccReminderDelivery.objects.create(
            record=self.record,
            requested_by=self.user,
            idempotency_key="dcc-reminder-005",
            message_id="<dcc-reminder-test@awcenter>",
            subject="Reminder subject",
            context=reminder_snapshot(self.record)["context"],
            recipients=["recipient@example.test"],
        )
        delivery_id, token = claim_dcc_reminders()[0]

        delivered = deliver_dcc_reminder(delivery_id, token)

        self.assertTrue(delivered)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, DccReminderDelivery.Status.SENT)
        self.assertEqual(delivery.recipient_count, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].extra_headers["Message-ID"], delivery.message_id)


def reminder_snapshot(record):
    return {
        "subject": "[HYS] CCB - 12 toplantı gündemi",
        "recipients": ["recipient@example.test"],
        "context": {
            "issue": record.issue,
            "title": record.title,
            "jira_url": f"https://jira.example.test/browse/{record.issue}",
            "project_labels": ["HYS"],
            "ccb_no": 12,
            "due_date": "2026-09-10",
            "record_id": str(record.id),
            "record_version": record.version,
        },
    }
