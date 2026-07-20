from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.action_center_models import ActionCenterDecision
from jobs.models import JobStatus

from .test_action_center import (
    create_failed_job,
    create_jira_draft,
    create_job,
    create_partial_audit,
)

User = get_user_model()


class ActionCenterDecisionTests(TestCase):
    """Verify private, authorized snooze and dismissal decisions."""

    def setUp(self):
        """Create two audit viewers and one authenticated client."""

        permission = Permission.objects.get(codename="view_compdocimportaudit")
        self.user = User.objects.create_user("decision-user", password="StrongPass!123")
        self.other = User.objects.create_user("decision-other", password="StrongPass!123")
        self.user.user_permissions.add(permission)
        self.other.user_permissions.add(permission)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_snooze_hides_item_for_one_day_then_reveals_it(self):
        """Expired snoozes no longer suppress an unresolved source item."""

        job = create_failed_job(self.user, "Temporarily hidden")
        item_id = f"job:{job.pk}"

        response = self.post_decision(item_id, "snooze")
        hidden = self.client.get("/action-center/")
        ActionCenterDecision.objects.update(snoozed_until=timezone.now() - timedelta(seconds=1))
        visible = self.client.get("/action-center/")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(hidden.data["items"], [])
        self.assertEqual(visible.data["items"][0]["id"], item_id)

    def test_dismissal_is_user_specific_and_updates_existing_decision(self):
        """One user's terminal decision never hides another viewer's audit."""

        audit = create_partial_audit()
        item_id = f"import:{audit.pk}"
        self.post_decision(item_id, "snooze")
        self.post_decision(item_id, "dismiss")
        dismissed = self.client.get("/action-center/")
        self.client.force_authenticate(self.other)
        other_view = self.client.get("/action-center/")

        decision = ActionCenterDecision.objects.get(user=self.user, item_key=item_id)
        self.assertIsNotNone(decision.acknowledged_at)
        self.assertIsNone(decision.snoozed_until)
        self.assertEqual(ActionCenterDecision.objects.count(), 1)
        self.assertEqual(dismissed.data["items"], [])
        self.assertEqual(other_view.data["items"][0]["id"], item_id)

    def test_decision_rejects_another_users_item_and_invalid_actions(self):
        """Clients cannot create arbitrary or unauthorized suppression records."""

        private_job = create_failed_job(self.other, "Private failure")
        unavailable = self.post_decision(f"job:{private_job.pk}", "dismiss")
        invalid = self.post_decision(f"job:{private_job.pk}", "later")

        self.assertEqual(unavailable.status_code, 400)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(ActionCenterDecision.objects.count(), 0)

    def test_jira_draft_identifier_supports_decisions(self):
        """The decision contract accepts the existing unresolved JIRA draft item kind."""

        source = create_job(self.user, "Analysis", JobStatus.SUCCEEDED)
        draft = create_jira_draft(self.user, source, "approved")

        response = self.post_decision(f"jira-draft:{draft.pk}", "dismiss")

        self.assertEqual(response.status_code, 204)
        self.assertTrue(ActionCenterDecision.objects.filter(user=self.user).exists())

    def post_decision(self, item_id, action):
        """Post one action-center decision using the authenticated client."""

        return self.client.post(
            "/action-center/decisions/",
            {"item_id": item_id, "action": action},
            format="json",
        )
