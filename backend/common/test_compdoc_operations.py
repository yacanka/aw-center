from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from awcenter.action_center import build_action_center
from common.compdoc_import_test_utils import grant_model_permissions
from projects.ozgur.models import CompDoc


class CompDocOperationsTests(TestCase):
    """Verify bounded bulk, ownership, assignment, and archive operations."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("operations-user")
        grant_model_permissions(self.user, CompDoc, "view", "change", "delete")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.document = CompDoc.objects.create(name="Manual", cover_page_no="CP-OPS")

    def test_bulk_stale_version_rolls_back_entire_batch(self):
        second = CompDoc.objects.create(name="Second", cover_page_no="CP-SECOND")
        response = self.client.post(
            "/ozgur/compdocs/bulk/",
            {
                "documents": [
                    {
                        "id": str(self.document.pk),
                        "source_history_id": self.document.history.first().history_id,
                    },
                    {
                        "id": str(second.pk),
                        "source_history_id": second.history.first().history_id + 1,
                    },
                ],
                "action": "archive",
                "reason": "Archive superseded documents",
            },
            format="json",
        )
        self.document.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.document.is_archived)
        self.assertFalse(second.is_archived)

    def test_archived_documents_are_hidden_by_default_and_restorable(self):
        archived = self.client.post(
            f"/ozgur/compdocs/{self.document.pk}/archive/",
            {
                "source_history_id": self.document.history.first().history_id,
            },
            format="json",
        )
        hidden = self.client.get("/ozgur/compdocs/")
        visible = self.client.get("/ozgur/compdocs/", {"archived": "true"})
        restored = self.client.post(
            f"/ozgur/compdocs/{self.document.pk}/restore/",
            {
                "source_history_id": archived.data["source_history_id"],
            },
            format="json",
        )
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(hidden.data["count"], 0)
        self.assertEqual(visible.data["count"], 1)
        self.assertEqual(restored.status_code, 200)

    def test_work_assignment_allows_omitted_reason(self):
        response = self.client.put(
            f"/ozgur/compdocs/{self.document.pk}/work/",
            {
                "source_history_id": self.document.history.first().history_id,
                "owner": self.user.pk,
            },
            format="json",
        )
        self.document.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.document.owner, self.user)

    def test_bulk_operation_allows_omitted_reason(self):
        response = self.client.post(
            "/ozgur/compdocs/bulk/",
            {
                "documents": [
                    {
                        "id": str(self.document.pk),
                        "source_history_id": self.document.history.first().history_id,
                    }
                ],
                "action": "archive",
            },
            format="json",
        )
        self.document.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.document.is_archived)

    def test_work_assignment_rejects_user_without_project_access(self):
        outsider = get_user_model().objects.create_user("project-outsider")
        response = self.client.put(
            f"/ozgur/compdocs/{self.document.pk}/work/",
            {
                "source_history_id": self.document.history.first().history_id,
                "owner": outsider.pk,
                "reason": "Assign daily document ownership",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(CompDoc.objects.get(pk=self.document.pk).owner)

    def test_assignee_search_omits_personal_contact_data(self):
        assignee = get_user_model().objects.create_user(
            "visible-assignee", email="private@example.test"
        )
        grant_model_permissions(assignee, CompDoc, "view")
        response = self.client.get("/ozgur/compdocs/assignees/", {"search": "visible"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["users"][0]["username"], "visible-assignee")
        self.assertNotIn("email", response.data["users"][0])

    def test_owner_due_date_appears_in_personal_action_center(self):
        self.document.owner = self.user
        self.document.next_action_due_date = timezone.localdate()
        self.document.save(update_fields=["owner", "next_action_due_date"])
        payload = build_action_center(self.user)
        self.assertTrue(any(item["kind"] == "compdoc_owner" for item in payload["items"]))
