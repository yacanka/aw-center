"""Durability and credential-boundary tests for Watcher reminder mail."""

from datetime import timedelta
import uuid
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment

from .models import DccRecord, DccReminderDelivery
from .reminder_notifications import (
    claim_dcc_reminders, deliver_dcc_reminder, process_dcc_reminder_deliveries,
)


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

    @override_settings(
        AWCENTER_MAIL_TRANSPORT="django",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_timeout_retries_and_claims_next_reminder_only_when_ready(self):
        from integrations.mail import send_html_email

        first = self.create_delivery("timeout-first")
        second = self.create_delivery("timeout-second")

        def smtp_send(subject, body, recipients, **kwargs):
            if kwargs["message_id"] == first.message_id:
                second.refresh_from_db()
                self.assertEqual(second.status, DccReminderDelivery.Status.PENDING)
                raise TimeoutError("private upstream timeout detail")
            send_html_email(subject, body, recipients, **kwargs)

        with patch("dcc.reminder_notifications.send_html_email", side_effect=smtp_send):
            result = process_dcc_reminder_deliveries()
        self.assertEqual(result, {"processed": 2, "sent": 1, "failed": 1})
        first.refresh_from_db()
        self.assertEqual(first.error_code, "MAIL_DELIVERY_TIMEOUT")
        self.assertIsNotNone(first.next_attempt_at)
        self.assertIsNone(first.lease_token)
        first.next_attempt_at = timezone.now()
        first.save(update_fields=["next_attempt_at"])
        self.assertEqual(process_dcc_reminder_deliveries()["sent"], 1)
        first.refresh_from_db()
        self.assertEqual(first.status, DccReminderDelivery.Status.SENT)
        self.assertEqual(mail.outbox[-1].extra_headers["Message-ID"], first.message_id)

    def test_expired_reminder_lease_cannot_send(self):
        delivery = self.create_delivery("expired")
        delivery_id, token = claim_dcc_reminders()[0]
        DccReminderDelivery.objects.filter(pk=delivery_id).update(
            claim_expires_at=timezone.now() - timedelta(seconds=1),
        )
        with patch("dcc.reminder_notifications.send_html_email") as smtp_send:
            self.assertFalse(deliver_dcc_reminder(delivery_id, token))
        smtp_send.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, DccReminderDelivery.Status.CLAIMED)

    def test_timeout_after_reclaim_preserves_new_reminder_lease(self):
        delivery = self.create_delivery("reclaimed")
        delivery_id, token = claim_dcc_reminders()[0]
        new_token = uuid.uuid4()

        def timeout_after_reclaim(*args, **kwargs):
            DccReminderDelivery.objects.filter(pk=delivery_id).update(lease_token=new_token)
            raise TimeoutError()

        with patch("dcc.reminder_notifications.send_html_email", side_effect=timeout_after_reclaim):
            self.assertFalse(deliver_dcc_reminder(delivery_id, token))
        delivery.refresh_from_db()
        self.assertEqual(delivery.lease_token, new_token)
        self.assertEqual(delivery.status, DccReminderDelivery.Status.CLAIMED)

    def create_delivery(self, key):
        return DccReminderDelivery.objects.create(
            record=self.record, requested_by=self.user, idempotency_key=key,
            message_id=f"<{key}@awcenter>", subject="Reminder subject",
            context=reminder_snapshot(self.record)["context"],
            recipients=["recipient@example.invalid"],
        )

    def test_timeout_after_lease_expiry_leaves_claim_recoverable(self):
        delivery = self.create_delivery("expired-timeout")
        delivery_id, token = claim_dcc_reminders()[0]

        def expired_timeout(*args, **kwargs):
            DccReminderDelivery.objects.filter(pk=delivery_id).update(
                claim_expires_at=timezone.now() - timedelta(seconds=1),
            )
            raise TimeoutError()

        with patch("dcc.reminder_notifications.send_html_email", side_effect=expired_timeout):
            self.assertFalse(deliver_dcc_reminder(delivery_id, token))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, DccReminderDelivery.Status.CLAIMED)
        self.assertEqual(delivery.lease_token, token)
        self.assertEqual(delivery.error_code, "")

    @override_settings(
        AWCENTER_MAIL_TRANSPORT="django", COMPDOC_NOTIFICATION_BATCH_SIZE=2,
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_lease_overrun_is_not_reclaimed_again_in_same_pass(self):
        from integrations.mail import send_html_email

        first = self.create_delivery("overrun-first")
        second = self.create_delivery("overrun-second")

        def overrun(subject, body, recipients, **kwargs):
            if kwargs["message_id"] == first.message_id:
                DccReminderDelivery.objects.filter(pk=first.pk).update(
                    claim_expires_at=timezone.now() - timedelta(seconds=1),
                )
            send_html_email(subject, body, recipients, **kwargs)

        with patch("dcc.reminder_notifications.send_html_email", side_effect=overrun):
            process_dcc_reminder_deliveries()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.attempt_count, 1)
        self.assertEqual(first.status, DccReminderDelivery.Status.CLAIMED)
        self.assertEqual(second.status, DccReminderDelivery.Status.SENT)
        self.assertEqual(process_dcc_reminder_deliveries()["sent"], 1)
        first.refresh_from_db()
        self.assertEqual(first.status, DccReminderDelivery.Status.SENT)


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
