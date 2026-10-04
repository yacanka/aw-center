"""Notification idempotency, lease fencing, and delivery tests."""

from datetime import timedelta
from io import StringIO
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from orgs.models import Panel, Person, Project, ResponsibleAssignment

from .models import ComplianceDocument, CoverPage, NotificationLog, TrackingProfile
from .notifications import (
    claim_notifications,
    deliver_notification,
    materialize_profile_events,
    scan_notifications,
)


@override_settings(
    AWCENTER_MAIL_TRANSPORT="django",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="no-reply@example.invalid",
)
class ComplianceNotificationTests(TestCase):
    def setUp(self):
        project = Project.objects.get(slug="ozgur")
        self.project = project
        panel = Panel.objects.create(
            project=project,
            name="Flight",
            discipline="Systems",
            ata="27-00",
        )
        person = Person.objects.create(
            person_id="10001",
            name="Ada Engineer",
            email="ada@example.com",
        )
        ResponsibleAssignment.objects.create(
            panel=panel,
            person=person,
            responsibility_role="AS",
        )
        cover = CoverPage.objects.create(project=project, number="CP-N")
        document = ComplianceDocument.objects.create(
            project=project,
            panel=panel,
            cover_page=cover,
            name="Notification document",
            status="to_be_issued",
            ubm_target_date=timezone.localdate() - timedelta(days=1),
        )
        self.profile = TrackingProfile.objects.create(
            document=document,
            notification_enabled=True,
            notification_events=["overdue"],
        )

    def test_materialization_is_idempotent_and_message_id_is_stable(self):
        self.assertEqual(materialize_profile_events(self.profile), 1)
        first = NotificationLog.objects.get()
        self.assertEqual(materialize_profile_events(self.profile), 0)

        self.assertEqual(NotificationLog.objects.count(), 1)
        self.assertEqual(first.message_id, f"<{first.event_key}@awcenter>")

    def test_revised_target_replaces_original_for_due_notifications(self):
        self.profile.document.ubm_revised_target_date = timezone.localdate() + timedelta(days=30)
        self.profile.document.save(update_fields=["ubm_revised_target_date"])
        self.assertEqual(materialize_profile_events(self.profile), 0)

    def test_delivery_suppresses_target_overdue_notification(self):
        self.profile.document.ubm_delivery_date = timezone.localdate() - timedelta(days=2)
        self.profile.document.save(update_fields=["ubm_delivery_date"])
        self.assertEqual(materialize_profile_events(self.profile), 0)

    def test_delivery_cancels_queued_target_notification(self):
        materialize_profile_events(self.profile)
        self.profile.document.ubm_delivery_date = timezone.localdate()
        self.profile.document.save(update_fields=["ubm_delivery_date"])

        result = scan_notifications(project_slug=self.project.slug)

        self.assertEqual(result["cancelled"], 1)
        self.assertEqual(NotificationLog.objects.get(profile=self.profile).status, NotificationLog.Status.CANCELLED)
        self.assertEqual(len(mail.outbox), 0)

    def test_only_current_lease_can_publish_terminal_state(self):
        materialize_profile_events(self.profile)
        log_id, token = claim_notifications()[0]

        self.assertFalse(deliver_notification(log_id, uuid.uuid4()))
        self.assertTrue(deliver_notification(log_id, token))

        log = NotificationLog.objects.get(pk=log_id)
        self.assertEqual(log.status, NotificationLog.Status.SENT)
        self.assertEqual(log.recipient_count, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].extra_headers["Message-ID"], log.message_id)

    def test_delivery_sanitizes_a_legacy_multiline_document_name(self):
        self.profile.document.name = "Legacy\nDocument"
        self.profile.document.save(update_fields=["name"])
        materialize_profile_events(self.profile)
        log_id, token = claim_notifications()[0]

        self.assertTrue(deliver_notification(log_id, token))

        self.assertEqual(mail.outbox[0].subject, "AW Center compliance alert: Legacy Document")

    def test_project_scan_does_not_claim_another_projects_notification(self):
        other_project = Project.objects.get(slug="piku")
        other_panel = Panel.objects.create(
            project=other_project,
            name="Other Flight",
            discipline="Systems",
            ata="28-00",
        )
        other_person = Person.objects.create(
            person_id="10002",
            name="Other Engineer",
            email="other@example.com",
        )
        ResponsibleAssignment.objects.create(
            panel=other_panel,
            person=other_person,
            responsibility_role="AS",
        )
        other_profile = TrackingProfile.objects.create(
            document=ComplianceDocument.objects.create(
                project=other_project,
                panel=other_panel,
                cover_page=CoverPage.objects.create(project=other_project, number="CP-O"),
                name="Other notification document",
                status="to_be_issued",
                ubm_target_date=timezone.localdate() - timedelta(days=1),
            ),
            notification_enabled=True,
            notification_events=["overdue"],
        )
        materialize_profile_events(other_profile)

        result = scan_notifications(project_slug=self.project.slug)

        other_log = NotificationLog.objects.get(profile=other_profile)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(other_log.status, NotificationLog.Status.PENDING)
        self.assertEqual(len(mail.outbox), 1)

    def test_stale_event_is_cancelled_before_delivery(self):
        materialize_profile_events(self.profile)
        self.profile.document.ubm_target_date = timezone.localdate() + timedelta(days=30)
        self.profile.document.save(update_fields=["ubm_target_date"])

        result = scan_notifications(project_slug=self.project.slug)

        log = NotificationLog.objects.get(profile=self.profile)
        self.assertEqual(result["cancelled"], 1)
        self.assertEqual(log.status, NotificationLog.Status.CANCELLED)
        self.assertEqual(len(mail.outbox), 0)

    def test_timeout_retries_and_claims_next_notification_only_when_ready(self):
        from integrations.mail import send_html_email

        materialize_profile_events(self.profile)
        first = NotificationLog.objects.get()
        self.profile.notification_events = ["overdue", "revision_available"]
        self.profile.docproof_status = "revision_available"
        self.profile.docproof_issue = "B"
        self.profile.save()
        materialize_profile_events(self.profile)
        second = NotificationLog.objects.get(event_type="revision_available")

        def smtp_send(subject, body, recipients, **kwargs):
            if kwargs["message_id"] == first.message_id:
                second.refresh_from_db()
                self.assertEqual(second.status, NotificationLog.Status.PENDING)
                raise TimeoutError("private upstream timeout detail")
            send_html_email(subject, body, recipients, **kwargs)

        with patch("compliance.notifications.send_html_email", side_effect=smtp_send):
            result = scan_notifications()
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["failed"], 1)
        first.refresh_from_db()
        self.assertEqual(first.error_code, "MAIL_DELIVERY_TIMEOUT")
        self.assertIsNotNone(first.next_attempt_at)
        self.assertIsNone(first.lease_token)
        first.next_attempt_at = timezone.now()
        first.save(update_fields=["next_attempt_at"])
        self.assertEqual(scan_notifications()["sent"], 1)
        first.refresh_from_db()
        self.assertEqual(first.status, NotificationLog.Status.SENT)
        self.assertEqual(mail.outbox[-1].extra_headers["Message-ID"], first.message_id)

    def test_expired_notification_lease_cannot_send(self):
        materialize_profile_events(self.profile)
        log_id, token = claim_notifications()[0]
        NotificationLog.objects.filter(pk=log_id).update(
            claim_expires_at=timezone.now() - timedelta(seconds=1),
        )
        with patch("compliance.notifications.send_html_email") as smtp_send:
            self.assertFalse(deliver_notification(log_id, token))
        smtp_send.assert_not_called()
        self.assertEqual(NotificationLog.objects.get(pk=log_id).status, NotificationLog.Status.CLAIMED)

    def test_timeout_after_reclaim_preserves_new_notification_lease(self):
        materialize_profile_events(self.profile)
        log_id, token = claim_notifications()[0]
        new_token = uuid.uuid4()

        def timeout_after_reclaim(*args, **kwargs):
            NotificationLog.objects.filter(pk=log_id).update(lease_token=new_token)
            raise TimeoutError()

        with patch("compliance.notifications.send_html_email", side_effect=timeout_after_reclaim):
            self.assertFalse(deliver_notification(log_id, token))
        log = NotificationLog.objects.get(pk=log_id)
        self.assertEqual(log.lease_token, new_token)
        self.assertEqual(log.status, NotificationLog.Status.CLAIMED)

    def test_worker_continues_other_queues_after_password_reset_timeout(self):
        from dcc.models import DccReminderDelivery
        from users.models import PasswordResetDelivery
        from users.password_reset_notifications import enqueue_password_reset

        user = get_user_model().objects.create_user(
            "timeout-worker-user", email="reset@example.invalid", password="pass",
        )
        reset, _ = enqueue_password_reset(user)
        reminder = DccReminderDelivery.objects.create(
            requested_by=user, idempotency_key="worker-timeout",
            message_id="<worker-timeout@awcenter>", subject="Reminder",
            context={}, recipients=["recipient@example.invalid"],
        )
        with patch("users.password_reset_notifications.send_html_email", side_effect=TimeoutError()):
            call_command(
                "run_compdoc_notification_worker", once=True,
                stdout=StringIO(), stderr=StringIO(),
            )
        reset.refresh_from_db()
        reminder.refresh_from_db()
        self.assertEqual(reset.status, PasswordResetDelivery.Status.FAILED)
        self.assertEqual(reminder.status, DccReminderDelivery.Status.SENT)
        self.assertEqual(NotificationLog.objects.get().status, NotificationLog.Status.SENT)
        self.assertEqual(len(mail.outbox), 2)

    def test_timeout_after_lease_expiry_leaves_claim_recoverable(self):
        materialize_profile_events(self.profile)
        log_id, token = claim_notifications()[0]

        def expired_timeout(*args, **kwargs):
            NotificationLog.objects.filter(pk=log_id).update(
                claim_expires_at=timezone.now() - timedelta(seconds=1),
            )
            raise TimeoutError()

        with patch("compliance.notifications.send_html_email", side_effect=expired_timeout):
            self.assertFalse(deliver_notification(log_id, token))
        log = NotificationLog.objects.get(pk=log_id)
        self.assertEqual(log.status, NotificationLog.Status.CLAIMED)
        self.assertEqual(log.lease_token, token)
        self.assertEqual(log.error_code, "")

    @override_settings(COMPDOC_NOTIFICATION_BATCH_SIZE=2)
    def test_lease_overrun_is_not_reclaimed_again_in_same_pass(self):
        from integrations.mail import send_html_email

        materialize_profile_events(self.profile)
        first = NotificationLog.objects.get()
        self.profile.notification_events = ["overdue", "revision_available"]
        self.profile.docproof_status = "revision_available"
        self.profile.docproof_issue = "B"
        self.profile.save()
        materialize_profile_events(self.profile)
        second = NotificationLog.objects.get(event_type="revision_available")

        def overrun(subject, body, recipients, **kwargs):
            if kwargs["message_id"] == first.message_id:
                NotificationLog.objects.filter(pk=first.pk).update(
                    claim_expires_at=timezone.now() - timedelta(seconds=1),
                )
            send_html_email(subject, body, recipients, **kwargs)

        with patch("compliance.notifications.send_html_email", side_effect=overrun):
            scan_notifications()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.attempt_count, 1)
        self.assertEqual(first.status, NotificationLog.Status.CLAIMED)
        self.assertEqual(second.status, NotificationLog.Status.SENT)
        self.assertEqual(scan_notifications()["sent"], 1)
        first.refresh_from_db()
        self.assertEqual(first.status, NotificationLog.Status.SENT)
