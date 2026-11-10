"""Notification rollout preservation and independent-connection regressions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
from threading import Barrier, Event
import uuid

from django.core import mail
from django.db import connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from orgs.models import Panel, Person, Project, ResponsibleAssignment

from .models import ComplianceDocument, CoverPage, NotificationLog, TrackingProfile
from .notifications import (
    _finish_success, claim_notifications, deliver_notification,
    materialize_profile_events, notification_is_enabled, scan_notifications,
)


@override_settings(
    DEBUG=False,
    AWCENTER_DEPLOYMENT_MODE="windows-native",
    AWCENTER_MAIL_TRANSPORT="django",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="no-reply@example.invalid",
)
class NotificationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        project, _ = Project.objects.get_or_create(slug="ozgur", defaults={"name": "Ozgur"})
        panel = Panel.objects.create(project=project, name="Panel", discipline="Systems", ata="27")
        person = Person.objects.create(person_id="notification-race", name="Engineer", email="engineer@example.invalid")
        ResponsibleAssignment.objects.create(panel=panel, person=person, responsibility_role="AS")
        self.profile = TrackingProfile.objects.create(
            document=ComplianceDocument.objects.create(
                project=project, panel=panel, name="Test document", number="DOC-ONE",
                cover_page=CoverPage.objects.create(project=project, number="CP-RACE"),
            ),
            notification_enabled=True, notification_events=["revision_available"],
            docproof_status="revision_available", docproof_issue="B",
        )

    def race(self, operation):
        barrier = Barrier(2)
        def run():
            try:
                barrier.wait(timeout=5)
                return operation()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda _: run(), range(2), timeout=15))

    def test_concurrent_materialization_and_claim_produce_one_delivery(self):
        self.assertCountEqual(self.race(lambda: materialize_profile_events(self.profile)), [0, 1])
        claims = self.race(lambda: claim_notifications(limit=1))
        self.assertCountEqual([len(result) for result in claims], [0, 1])
        log_id, token = next(result[0] for result in claims if result)
        self.assertTrue(deliver_notification(log_id, token))
        self.assertFalse(deliver_notification(log_id, token))
        self.assertEqual(NotificationLog.objects.get().attempt_count, 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_concurrent_scans_send_one_message(self):
        results = self.race(scan_notifications)
        self.assertEqual(sum(result["sent"] for result in results), 1)
        self.assertEqual(NotificationLog.objects.get().status, NotificationLog.Status.SENT)
        self.assertEqual(len(mail.outbox), 1)

    def test_materialization_waits_for_number_update_and_reads_cleared_evidence(self):
        changed, release, started = Event(), Event(), Event()
        def update_number():
            try:
                with transaction.atomic():
                    document = ComplianceDocument.objects.select_for_update().get(pk=self.profile.document_id)
                    document.number = "DOC-TWO"
                    document.save(update_fields=["number"])
                    TrackingProfile.objects.filter(pk=self.profile.pk).update(
                        docproof_status="never_checked", docproof_issue="",
                    )
                    changed.set()
                    if not release.wait(5):
                        raise TimeoutError("Number update was not released")
            finally:
                connections.close_all()
        def materialize():
            try:
                started.set()
                return materialize_profile_events(self.profile)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(update_number)
            try:
                self.assertTrue(changed.wait(5))
                scanner = pool.submit(materialize)
                self.assertTrue(started.wait(5))
            finally:
                release.set()
            writer.result(timeout=5)
            self.assertEqual(scanner.result(timeout=5), 0)
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_reclaimed_delivery_rejects_old_completion_and_keeps_message_id(self):
        materialize_profile_events(self.profile)
        log_id, old_token = claim_notifications()[0]
        message_id = NotificationLog.objects.get(pk=log_id).message_id
        NotificationLog.objects.filter(pk=log_id).update(claim_expires_at=timezone.now() - timedelta(seconds=1))
        _, new_token = claim_notifications()[0]
        self.assertNotEqual(old_token, new_token)
        self.assertFalse(_finish_success(log_id, old_token, 1))
        self.assertTrue(deliver_notification(log_id, new_token))
        self.assertEqual(NotificationLog.objects.get(pk=log_id).message_id, message_id)
        self.assertEqual(len(mail.outbox), 1)


@override_settings(
    DEBUG=False,
    AWCENTER_MAIL_TRANSPORT="django",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="no-reply@example.invalid",
)
class NotificationIdentityMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_history_claims_and_does_not_bulk_resend(self):
        old_target = [("compliance", "0003_seed_default_statuses")]
        new_target = [("compliance", "0004_revision_notification_identity")]
        executor = MigrationExecutor(connection)
        # This data-only migration has no reverse transform: on this empty test
        # database, reset only its migration record to exercise the real upgrade.
        executor.migrate(old_target, fake=True)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(new_target))
        old_apps = executor.loader.project_state(old_target).apps
        projects = old_apps.get_model("orgs", "Project")
        project, _ = projects.objects.get_or_create(slug="ozgur", defaults={"name": "Ozgur"})
        cover = old_apps.get_model("compliance", "CoverPage").objects.create(project_id=project.pk, number="CP-UPGRADE")
        documents = old_apps.get_model("compliance", "ComplianceDocument")
        profiles = old_apps.get_model("compliance", "TrackingProfile")
        logs = old_apps.get_model("compliance", "NotificationLog")
        saved = []
        for status in ("sent", "pending", "claimed", "failed", "cancelled"):
            document = documents.objects.create(project_id=project.pk, cover_page_id=cover.pk, name=status, number="DOC-OLD")
            profile = profiles.objects.create(
                document_id=document.pk, notification_enabled=True,
                notification_events=["revision_available"], docproof_status="revision_available", docproof_issue="B",
            )
            key = hashlib.sha256(f"{profile.pk}:revision_available:B".encode()).hexdigest()
            token = uuid.uuid4() if status == "claimed" else None
            log = logs.objects.create(
                profile_id=profile.pk, event_type="revision_available", event_key=key,
                message_id=f"<{key}@awcenter>", status=status, lease_token=token,
                claim_expires_at=timezone.now() + timedelta(minutes=10) if token else None,
                attempt_count=2, recipient_count=1 if status == "sent" else 0,
                sent_at=timezone.now() if status == "sent" else None,
                error_code="MAIL_DELIVERY_TIMEOUT" if status == "failed" else "",
            )
            saved.append(logs.objects.values().get(pk=log.pk))
        MigrationExecutor(connection).migrate(new_target)
        for before in saved:
            after = NotificationLog.objects.values().get(pk=before["id"])
            self.assertNotEqual(after.pop("event_key"), before.pop("event_key"))
            self.assertEqual(after, before)
            profile = TrackingProfile.objects.get(pk=before["profile_id"])
            self.assertEqual(materialize_profile_events(profile), 0)
            migrated = NotificationLog.objects.get(pk=before["id"])
            self.assertTrue(notification_is_enabled(profile, migrated.event_type, migrated.event_key))
        self.assertEqual(NotificationLog.objects.count(), 5)
        sent = NotificationLog.objects.get(status="sent")
        self.assertEqual(sent.attempt_count, 2)
        TrackingProfile.objects.exclude(pk=sent.profile_id).update(notification_enabled=False)
        self.assertEqual(scan_notifications()["sent"], 0)
        self.assertEqual(len(mail.outbox), 0)
        document = sent.profile.document
        document.number = "DOC-NEW"
        document.save(update_fields=["number"])
        self.assertEqual(materialize_profile_events(sent.profile), 1)
        self.assertEqual(materialize_profile_events(sent.profile), 0)
        self.assertEqual(NotificationLog.objects.count(), 6)
