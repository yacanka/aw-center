"""Notification idempotency, lease fencing, and delivery tests."""

from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.core import mail
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
