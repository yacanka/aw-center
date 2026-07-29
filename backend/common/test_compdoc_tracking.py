"""Compliance-document tracking, DocProof, and notification tests."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.compdoc_import_test_utils import grant_model_permissions
from common.compdoc_notification_scan import scan_enabled_profiles
from common.compdoc_tracking_models import (
    CompDocNotificationLog,
    CompDocTrackingProfile,
)
from orgs.models import People
from projects.ozgur.models import CompDoc, Panel, Responsible


class CompDocTrackingApiTests(TestCase):
    """Verify project permissions and ATA-backed responsible assignment."""

    def setUp(self):
        """Create one document and two responsibles on different ATA chapters."""

        self.user = get_user_model().objects.create_user("tracking-user", password="Pass!123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.panel = Panel.objects.create(name="Flight", discipline="Systems", ata="21-00")
        other_panel = Panel.objects.create(name="Power", discipline="Systems", ata="24-00")
        first_person = People.objects.create(
            person_id="100001", name="Ada Lovelace", email="ada@example.com"
        )
        second_person = People.objects.create(
            person_id="100002", name="Grace Hopper", email="grace@example.com"
        )
        self.responsible = Responsible.objects.create(
            panel=self.panel,
            person=first_person,
            title="CVE",
        )
        Responsible.objects.create(
            panel=other_panel,
            person=second_person,
            title="CVE",
        )
        self.document = CompDoc.objects.create(
            name="Flight Manual",
            cover_page_no="CP-TRACK",
            ata="21-00",
            tech_doc_no="TD-001",
            tech_doc_issue="2",
        )
        self.tracking_path = f"/ozgur/compdocs/{self.document.pk}/tracking/"

    def test_tracking_read_requires_view_and_auto_resolves_ata_contacts(self):
        denied = self.client.get(self.tracking_path)
        grant_model_permissions(self.user, CompDoc, "view")
        allowed = self.client.get(self.tracking_path)

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data["responsible_mode"], "automatic")
        self.assertEqual(allowed.data["responsible_person_ids"], [self.responsible.pk])
        self.assertFalse(allowed.data["configured"])
        self.assertEqual(len(allowed.data["event_states"]), 3)
        self.assertFalse(any(state["applicable"] for state in allowed.data["event_states"]))
        self.assertTrue(all(state["recipient_count"] == 1 for state in allowed.data["event_states"]))
        self.assertFalse(CompDocTrackingProfile.objects.exists())

    def test_custom_selection_requires_change_and_rejects_another_ata(self):
        payload = self._tracking_payload([self.responsible.pk])
        self.assertEqual(self.client.put(self.tracking_path, payload, format="json").status_code, 403)
        grant_model_permissions(self.user, CompDoc, "change")
        saved = self.client.put(self.tracking_path, payload, format="json")
        invalid = self.client.put(
            self.tracking_path,
            self._tracking_payload([999999]),
            format="json",
        )

        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.data["configured"])
        self.assertEqual(saved.data["responsible_person_ids"], [self.responsible.pk])
        self.assertEqual(invalid.status_code, 400)

    def test_tracking_payload_explains_an_applicable_due_soon_event(self):
        target = timezone.localdate() + timedelta(days=3)
        self.document.status_flow = [
            {"status": "to_be_issued", "date": target.isoformat()}
        ]
        self.document.save(update_fields=["status_flow"])
        grant_model_permissions(self.user, CompDoc, "view")

        response = self.client.get(self.tracking_path)
        state = next(
            item for item in response.data["event_states"] if item["value"] == "due_soon"
        )

        self.assertTrue(state["applicable"])
        self.assertIn("due in 3 day(s)", state["detail"])

    @patch("common.compdoc_docproof.search_issue_number", return_value=(3, None))
    def test_docproof_check_persists_explainable_revision_state(self, _search):
        grant_model_permissions(self.user, CompDoc, "change")
        response = self.client.post(f"/ozgur/compdocs/{self.document.pk}/docproof/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["docproof"]["status"], "revision_available")
        self.assertEqual(response.data["docproof"]["issue"], "3")

    @patch("common.compdoc_docproof.search_issue_number", return_value=(2, None))
    def test_docproof_numeric_issue_format_does_not_create_false_revision(self, _search):
        self.document.tech_doc_issue = "02"
        self.document.save()
        grant_model_permissions(self.user, CompDoc, "change")

        response = self.client.post(f"/ozgur/compdocs/{self.document.pk}/docproof/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["docproof"]["status"], "current")

    def test_document_archive_preserves_its_tracking_profile(self):
        grant_model_permissions(self.user, CompDoc, "change", "delete")
        saved = self.client.put(
            self.tracking_path,
            self._tracking_payload([self.responsible.pk]),
            format="json",
        )
        deleted = self.client.delete(f"/ozgur/compdocs/{self.document.pk}/")

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(deleted.status_code, 200)
        self.document.refresh_from_db()
        self.assertTrue(self.document.is_archived)
        self.assertTrue(CompDocTrackingProfile.objects.exists())

    def _tracking_payload(self, person_ids):
        return {
            "responsible_mode": "custom",
            "responsible_person_ids": person_ids,
            "notification_enabled": True,
            "notification_events": ["overdue", "revision_available"],
        }


class CompDocNotificationTests(TestCase):
    """Verify opt-in, idempotent, auditable HTML notification processing."""

    def setUp(self):
        """Create an overdue document with one automatic recipient."""

        panel = Panel.objects.create(name="Flight", discipline="Systems", ata="21-00")
        person = People.objects.create(
            person_id="100003", name="Katherine Johnson", email="katherine@example.com"
        )
        Responsible.objects.create(
            panel=panel,
            person=person,
            title="AS",
        )
        target = timezone.localdate() - timedelta(days=2)
        self.document = CompDoc.objects.create(
            name="Overdue Manual",
            cover_page_no="CP-LATE",
            ata="21-00",
            status_flow=[{"status": "to_be_issued", "date": target.isoformat()}],
        )
        self.profile = CompDocTrackingProfile.objects.create(
            project_slug="ozgur",
            document_id=self.document.pk,
            notification_enabled=True,
            notification_events=["overdue"],
        )

    @patch("common.compdoc_notifications.SendMail", return_value=True)
    def test_scan_sends_each_evidence_once_without_storing_message_body(self, sender):
        first = scan_enabled_profiles("ozgur")
        second = scan_enabled_profiles("ozgur")

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        sender.assert_called_once()
        log = CompDocNotificationLog.objects.get()
        self.assertEqual(log.status, "sent")
        self.assertEqual(log.recipient_count, 1)
        self.assertFalse(hasattr(log, "body"))

    @patch("common.compdoc_notifications.SendMail", return_value=False)
    def test_unavailable_transport_is_recorded_as_failure(self, _sender):
        result = scan_enabled_profiles("ozgur")

        self.assertEqual(result["failed"], 1)
        self.assertEqual(
            CompDocNotificationLog.objects.get().error_code,
            "COMPDOC_NOTIFICATION_DELIVERY_UNAVAILABLE",
        )
