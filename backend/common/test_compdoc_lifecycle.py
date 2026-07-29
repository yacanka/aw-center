from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

from common.compdoc_import_test_utils import grant_model_permissions
from common.compdoc_lifecycle_models import CompDocReviewTask, CompDocWorkflowEvent
from projects.ozgur.models import CompDoc


class CompDocLifecycleTests(TestCase):
    """Verify audited transitions and recoverable archive behavior."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("lifecycle-user")
        grant_model_permissions(self.user, CompDoc, "view", "change", "delete")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.document = CompDoc.objects.create(name="Manual", cover_page_no="CP-LIFE")

    def test_transition_appends_actor_attributed_event(self):
        response = self.client.post(
            f"/ozgur/compdocs/{self.document.pk}/transitions/",
            {
                "source_history_id": self.document.history.first().history_id,
                "status": "authority_review",
                "effective_date": "2026-07-29",
                "reason": "Submitted to authority",
            },
            format="json",
        )
        self.document.refresh_from_db()
        event = CompDocWorkflowEvent.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.document.status, "authority_review")
        self.assertEqual(event.actor, self.user)

    def test_transition_allows_omitted_reason(self):
        response = self.client.post(
            f"/ozgur/compdocs/{self.document.pk}/transitions/",
            {
                "source_history_id": self.document.history.first().history_id,
                "status": "authority_review",
                "effective_date": "2026-07-29",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CompDocWorkflowEvent.objects.get().reason, "")

    def test_legacy_delete_archives_without_removing_history(self):
        response = self.client.delete(f"/ozgur/compdocs/{self.document.pk}/")
        self.document.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.document.is_archived)
        self.assertGreaterEqual(self.document.history.count(), 2)

    def test_stale_transition_returns_conflict_without_event(self):
        response = self.client.post(
            f"/ozgur/compdocs/{self.document.pk}/transitions/",
            {
                "source_history_id": self.document.history.first().history_id + 99,
                "status": "authority_review",
                "effective_date": "2026-07-29",
                "reason": "Stale transition",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(CompDocWorkflowEvent.objects.exists())

    def test_regular_update_accepts_unchanged_workflow_projection(self):
        self.document.status_flow = [
            {"status": "to_be_issued", "date": "29.07.2026", "note": "Initial state"}
        ]
        self.document.save()
        response = self.client.patch(
            f"/ozgur/compdocs/{self.document.pk}/",
            {
                "notes": "Updated document note",
                "status_flow": self.document.status_flow,
                "source_history_id": self.document.history.first().history_id,
                "change_reason": "Clarified the document note",
            },
            format="json",
        )
        self.document.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.document.notes, "Updated document note")
        self.assertEqual(len(self.document.status_flow), 1)

    def test_regular_update_allows_omitted_change_reason(self):
        response = self.client.patch(
            f"/ozgur/compdocs/{self.document.pk}/",
            {
                "notes": "Updated without an explanation",
                "source_history_id": self.document.history.first().history_id,
            },
            format="json",
        )
        self.document.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.document.notes, "Updated without an explanation")

    def test_regular_update_rejects_changed_workflow_projection(self):
        response = self.client.patch(
            f"/ozgur/compdocs/{self.document.pk}/",
            {
                "status_flow": [
                    {"status": "authority_review", "date": "29.07.2026"}
                ],
                "source_history_id": self.document.history.first().history_id,
                "change_reason": "Attempted direct workflow update",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("status_flow", response.data["errors"])

    def test_activity_combines_workflow_and_masks_reference_path_values(self):
        version = self.document.history.first().history_id
        self.client.patch(
            f"/ozgur/compdocs/{self.document.pk}/",
            {
                "path": "/sensitive/internal/location",
                "source_history_id": version,
                "change_reason": "Correct the document reference",
            },
            format="json",
        )
        response = self.client.get(f"/ozgur/compdocs/{self.document.pk}/activity/")
        history = next(item for item in response.data["results"] if item["type"] == "history")
        path_change = next(
            change for change in history["changes"] if change["field"] == "path"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("old", path_change)
        self.assertNotIn("new", path_change)

    def test_review_decision_is_assignee_signed_and_does_not_change_status(self):
        assignee = get_user_model().objects.create_user("review-assignee")
        grant_model_permissions(assignee, CompDoc, "view")
        created = self.client.post(
            f"/ozgur/compdocs/{self.document.pk}/reviews/",
            {
                "kind": "approval",
                "assignee": assignee.pk,
                "due_date": "2026-08-01",
                "request_note": "Approve the current evidence",
                "source_history_id": self.document.history.first().history_id,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.client.force_authenticate(assignee)
        decided = self.client.post(
            f"/ozgur/compdocs/{self.document.pk}/reviews/{created.data['id']}/decision/",
            {"status": "approved", "decision_note": "Evidence reviewed and approved"},
            format="json",
        )
        self.document.refresh_from_db()
        task = CompDocReviewTask.objects.get()
        self.assertEqual(decided.status_code, 200)
        self.assertEqual(task.decided_by, assignee)
        self.assertEqual(self.document.status, "unknown")

    def test_editor_can_cancel_pending_review_without_changing_lifecycle(self):
        assignee = get_user_model().objects.create_user("cancel-assignee")
        grant_model_permissions(assignee, CompDoc, "view")
        task = CompDocReviewTask.objects.create(
            project_slug="ozgur",
            document_id=self.document.pk,
            kind=CompDocReviewTask.Kind.REVIEW,
            assignee=assignee,
            assignee_username=assignee.get_username(),
            requested_by=self.user,
            requested_by_username=self.user.get_username(),
            request_note="Review current evidence",
            source_history_id=self.document.history.first().history_id,
        )
        response = self.client.post(
            f"/ozgur/compdocs/{self.document.pk}/reviews/{task.pk}/decision/",
            {"status": "cancelled", "decision_note": "Request is no longer required"},
            format="json",
        )
        task.refresh_from_db()
        self.document.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(task.status, CompDocReviewTask.Status.CANCELLED)
        self.assertEqual(self.document.status, "unknown")

    def test_workflow_manager_can_cancel_without_project_permission(self):
        manager = get_user_model().objects.create_user("workflow-manager")
        manager.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="common",
                codename="manage_compdoc_workflow",
            )
        )
        task = CompDocReviewTask.objects.create(
            project_slug="ozgur",
            document_id=self.document.pk,
            kind=CompDocReviewTask.Kind.REVIEW,
            assignee=self.user,
            assignee_username=self.user.get_username(),
            requested_by=self.user,
            requested_by_username=self.user.get_username(),
            request_note="Review current evidence",
            source_history_id=self.document.history.first().history_id,
        )
        self.client.force_authenticate(manager)
        response = self.client.post(
            f"/ozgur/compdocs/{self.document.pk}/reviews/{task.pk}/decision/",
            {"status": "cancelled", "decision_note": "Administrative cancellation"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
