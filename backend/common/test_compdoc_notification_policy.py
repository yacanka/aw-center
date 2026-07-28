"""Versioned Compliance Document notification-policy tests."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIClient

from common.compdoc_import_test_utils import grant_model_permissions
from common.compdoc_notification_policy import (
    delivery_occurrence,
    retry_due,
    save_policy,
)
from common.compdoc_notifications import send_notification
from common.compdoc_tracking_models import (
    CompDocNotificationLog,
    CompDocNotificationPolicy,
    CompDocTrackingProfile,
)
from projects.registry import get_enabled_project_definitions
from projects.ozgur.models import CompDoc, Panel, Responsible


class CompDocNotificationPolicyApiTests(TestCase):
    """Verify authorization, validation, versioning, and audit history."""

    def setUp(self):
        """Create a project operator and policy endpoint."""

        self.user = get_user_model().objects.create_user("policy-user", password="Pass!123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.path = "/ozgur/compdocs/notification-policy/"

    def test_read_uses_project_view_permission_and_safe_defaults(self):
        denied = self.client.get(self.path)
        grant_model_permissions(self.user, CompDoc, "view")
        allowed = self.client.get(self.path)

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data["version"], 0)
        self.assertFalse(allowed.data["configured"])
        self.assertFalse(allowed.data["can_manage"])
        self.assertEqual(set(allowed.data["rules"]), self._event_keys())

    def test_save_requires_global_manager_and_rejects_stale_revision(self):
        grant_model_permissions(self.user, CompDoc, "view", "change")
        denied = self.client.put(self.path, self._payload(), format="json")
        self._grant_manage()
        saved = self.client.put(self.path, self._payload(), format="json")
        conflict = self.client.put(self.path, self._payload(), format="json")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data["version"], 1)
        self.assertTrue(saved.data["can_manage"])
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["code"], "COMPDOC_POLICY_VERSION_CONFLICT")
        self.assertIn("Reload", conflict.data["recovery_hint"])

    def test_new_revision_retains_immutable_operator_evidence(self):
        grant_model_permissions(self.user, CompDoc, "view", "change")
        self._grant_manage()
        first = self.client.put(self.path, self._payload(), format="json")
        payload = self._payload(expected_version=1, note="Escalate overdue events sooner")
        payload["rules"]["overdue"]["escalate_after_hours"] = 12
        second = self.client.put(self.path, payload, format="json")

        self.assertEqual((first.status_code, second.status_code), (200, 200))
        revisions = list(CompDocNotificationPolicy.objects.filter(project_slug="ozgur"))
        self.assertEqual([item.version for item in revisions], [2, 1])
        self.assertEqual([item.is_active for item in revisions], [True, False])
        self.assertEqual(revisions[0].updated_by_username, "policy-user")
        self.assertEqual(second.data["history"][0]["change_note"], payload["change_note"])

    def test_rejects_overlapping_primary_and_escalation_roles(self):
        grant_model_permissions(self.user, CompDoc, "change")
        self._grant_manage()
        payload = self._payload()
        payload["rules"]["overdue"]["escalation_titles"] = ["CVE"]

        response = self.client.put(self.path, payload, format="json")

        self.assertEqual(response.status_code, 400)

    def test_all_project_policy_routes_resolve(self):
        for definition in get_enabled_project_definitions():
            match = resolve(f"/{definition.slug}/compdocs/notification-policy/")
            self.assertEqual(match.url_name, "compdoc_notification_policy")

    def _grant_manage(self):
        self.user.user_permissions.add(
            Permission.objects.get(codename="manage_compdoc_notification_policy")
        )
        self.user.__dict__.pop("_perm_cache", None)
        self.user.__dict__.pop("_user_perm_cache", None)

    def _payload(self, expected_version=0, note="Initial controlled policy"):
        rule = {
            "reminder_interval_hours": 0,
            "failure_retry_hours": 2,
            "primary_titles": ["CVE"],
            "escalation_titles": ["AS"],
            "escalate_after_hours": 24,
        }
        return {
            "expected_version": expected_version,
            "change_note": note,
            "rules": {event: dict(rule) for event in self._event_keys()},
        }

    @staticmethod
    def _event_keys():
        return {"overdue", "due_soon", "revision_available"}


class CompDocNotificationPolicyDeliveryTests(TestCase):
    """Verify role tiers, cadence, retry, and content-free delivery evidence."""

    def setUp(self):
        """Create an overdue document with primary and escalation roles."""

        panel = Panel.objects.create(name="Flight", discipline="Systems", ata="21-00")
        for person_id, name, email, title in (
            ("200001", "Primary", "primary@example.com", "CVE"),
            ("200002", "Escalation", "escalation@example.com", "AS"),
        ):
            Responsible.objects.create(
                panel=panel, person_id=person_id, name=name, email=email, title=title
            )
        target = timezone.localdate() - timedelta(days=3)
        self.document = CompDoc.objects.create(
            name="Controlled Manual",
            cover_page_no="CP-POLICY",
            ata="21-00",
            status_flow=[{"status": "to_be_issued", "date": target.isoformat()}],
        )
        self.profile = CompDocTrackingProfile.objects.create(
            project_slug="ozgur",
            document_id=self.document.pk,
            notification_enabled=True,
            notification_events=["overdue"],
        )
        user = get_user_model().objects.create_user("policy-owner")
        save_policy("ozgur", self._rules(), "Define escalation tiers", 0, user)

    @patch("common.compdoc_notifications.SendMail", return_value=True)
    def test_delivery_uses_primary_to_and_escalation_cc(self, sender):
        result = send_notification(CompDoc, self.document, self.profile, "overdue")

        self.assertEqual(result["status"], "sent")
        self.assertEqual(sender.call_args.args[2], "primary@example.com")
        self.assertEqual(sender.call_args.args[3], "escalation@example.com")
        log = CompDocNotificationLog.objects.get()
        self.assertEqual((log.primary_recipient_count, log.escalation_recipient_count), (1, 1))
        self.assertEqual(log.policy_version, 1)

    def test_event_cadence_and_failure_retry_are_deterministic(self):
        started = timezone.now() - timedelta(hours=49)
        rule = self._rules()["overdue"]
        self.assertEqual(delivery_occurrence(rule, started), "24h-2")
        log = CompDocNotificationLog.objects.create(
            profile=self.profile,
            event_type="overdue",
            event_key="failed-policy-delivery",
            status="failed",
        )
        CompDocNotificationLog.objects.filter(pk=log.pk).update(
            updated_at=timezone.now() - timedelta(hours=3)
        )
        log.refresh_from_db()
        self.assertTrue(retry_due(log, rule))

    @staticmethod
    def _rules():
        rule = {
            "reminder_interval_hours": 24,
            "failure_retry_hours": 2,
            "primary_titles": ["CVE"],
            "escalation_titles": ["AS"],
            "escalate_after_hours": 24,
        }
        return {event: dict(rule) for event in ("overdue", "due_soon", "revision_available")}
