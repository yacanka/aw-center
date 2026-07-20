"""Regression tests for stale CompDoc-to-DCC Action Center risks."""

from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

from common.action_center_models import ActionCenterDecision
from dcc.models import DccCompdocTrace
from projects.ozgur.models import CompDoc

User = get_user_model()


class CompdocTraceActionCenterTests(TestCase):
    """Verify stale-source detection, authorization, resolution, and decisions."""

    def setUp(self):
        """Create one authorized viewer and one traced compliance document."""

        self.user = User.objects.create_user("trace-action-user", password="StrongPass!123")
        self.client = APIClient()
        self.document = CompDoc.objects.create(name="Flight Manual", cover_page_no="FM-1")
        self.compdoc_permission = permission("ozgur", "view_compdoc")
        self.dcc_permission = permission("dcc", "view_jira_dcc")
        self.user.user_permissions.add(self.compdoc_permission, self.dcc_permission)
        self.reload_user()

    def test_changed_source_appears_with_exact_deep_link(self):
        """A current source edit exposes the newest stale DCC without leaking content."""

        trace = self.create_trace()
        current = self.client.get("/action-center/")
        self.change_document("Updated Flight Manual")
        changed = self.client.get("/action-center/")
        item = changed.data["items"][0]

        self.assertEqual(current.data["items"], [])
        self.assertEqual(item["kind"], "compdoc_trace")
        self.assertEqual(item["severity"], "warning")
        self.assertIn(str(self.document.pk), item["action_path"])
        self.assertIn(str(trace.id), item["action_path"])
        self.assertIn("Document name", item["detail"])
        self.assertNotIn(trace.snapshot_fingerprint, str(item))

    def test_non_captured_change_does_not_create_false_dcc_warning(self):
        """A history advance outside the DCC register does not ask for regeneration."""

        self.create_trace()
        self.document.notes = "Internal note outside the DCC register"
        self.document.save(update_fields=["notes"])

        response = self.client.get("/action-center/")

        self.assertEqual(response.data["items"], [])

    def test_reference_change_is_explained_without_field_values(self):
        """Attention details name affected fields without exposing document values."""

        self.document.tech_doc_issue = "A"
        self.document.save(update_fields=["tech_doc_issue"])
        self.create_trace()
        self.document.tech_doc_issue = "Sensitive-B"
        self.document.save(update_fields=["tech_doc_issue"])

        item = self.client.get("/action-center/").data["items"][0]

        self.assertIn("Technical document references", item["detail"])
        self.assertNotIn("Sensitive-B", str(item))

    def test_both_dcc_and_project_permissions_are_required(self):
        """Neither a DCC-only nor a project-only viewer can discover stale provenance."""

        self.create_trace()
        self.change_document("Permission-sensitive update")
        self.user.user_permissions.remove(self.dcc_permission)
        self.reload_user()
        project_only = self.client.get("/action-center/")
        self.user.user_permissions.add(self.dcc_permission)
        self.user.user_permissions.remove(self.compdoc_permission)
        self.reload_user()
        dcc_only = self.client.get("/action-center/")

        self.assertEqual(project_only.data["items"], [])
        self.assertEqual(dcc_only.data["items"], [])

    def test_new_confirmation_resolves_the_stale_source_risk(self):
        """A newer trace captured from the current history removes the warning."""

        self.create_trace()
        self.change_document("Regenerated source")
        stale = self.client.get("/action-center/")
        self.create_trace(issue_key="DCC-2")
        resolved = self.client.get("/action-center/")

        self.assertEqual(stale.data["summary"]["warning"], 1)
        self.assertEqual(resolved.data["items"], [])

    def test_stale_version_can_be_snoozed_and_new_edit_resurfaces(self):
        """Decisions bind to one history version so a later change becomes visible again."""

        self.create_trace()
        self.change_document("First source update")
        first_item = self.client.get("/action-center/").data["items"][0]
        snoozed = self.client.post(
            "/action-center/decisions/",
            {"item_id": first_item["id"], "action": "snooze"},
            format="json",
        )
        self.change_document("Second source update")
        second_items = self.client.get("/action-center/").data["items"]

        self.assertEqual(snoozed.status_code, 204)
        self.assertEqual(ActionCenterDecision.objects.count(), 1)
        self.assertEqual(len(second_items), 1)
        self.assertNotEqual(second_items[0]["id"], first_item["id"])

    def create_trace(self, issue_key="DCC-1"):
        """Persist one trace using the document's current Simple History version."""

        return DccCompdocTrace.objects.create(
            job_id=uuid4(),
            job_input_sha256=uuid4().hex * 2,
            confirmed_by=self.user,
            issue_key=issue_key,
            project_slug="ozgur",
            compdoc_id=self.document.pk,
            source_history_id=self.document.history.first().history_id,
            snapshot_fingerprint="f" * 64,
        )

    def change_document(self, name):
        """Create a new current source history version."""

        self.document.name = name
        self.document.save(update_fields=["name"])

    def reload_user(self):
        """Refresh permission caches and reauthenticate the API client."""

        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_authenticate(self.user)


def permission(app_label, codename):
    """Return one unambiguous model permission fixture."""

    return Permission.objects.get(content_type__app_label=app_label, codename=codename)
