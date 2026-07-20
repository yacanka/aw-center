"""Authorization and destructive confirmation tests for project CompDocs."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from projects.ozgur.models import CompDoc

from .compdoc_import_test_utils import grant_model_permissions, valid_row, workbook_upload


class CompDocPermissionTests(TestCase):
    """Verify project model actions are enforced at every CompDoc boundary."""

    def setUp(self):
        """Create isolated users and one representative document."""

        user_model = get_user_model()
        self.user = user_model.objects.create_user("compdoc-user", password="StrongPass!123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.document = CompDoc.objects.create(name="Flight Manual", cover_page_no="CP-PERM")

    def test_authenticated_user_without_view_permission_is_denied(self):
        """Authentication alone cannot read compliance data or metadata."""

        responses = [
            self.client.get("/ozgur/compdocs/"),
            self.client.get("/ozgur/compdocs/fields/"),
            self.client.get(f"/ozgur/compdocs/{self.document.id}/"),
            self.client.get(f"/ozgur/compdocs/{self.document.id}/history/"),
            self.client.get("/ozgur/compdocs/excel/"),
        ]

        self.assertTrue(all(response.status_code == 403 for response in responses))

    def test_view_permission_allows_uuid_detail_history_and_export(self):
        """Read permission covers list, UUID detail, history, fields, and export."""

        grant_model_permissions(self.user, CompDoc, "view")
        paths = [
            "/ozgur/compdocs/",
            "/ozgur/compdocs/fields/",
            f"/ozgur/compdocs/{self.document.id}/",
            f"/ozgur/compdocs/{self.document.id}/history/",
            "/ozgur/compdocs/excel/",
        ]

        self.assertTrue(all(self.client.get(path).status_code == 200 for path in paths))

    def test_mutations_require_their_specific_model_permissions(self):
        """Create, update, and delete permissions cannot substitute for each other."""

        payload = {"name": "New Manual", "cover_page_no": "CP-NEW", "ata": "00-00"}
        self.assertEqual(self.client.post("/ozgur/compdocs/", payload).status_code, 403)
        grant_model_permissions(self.user, CompDoc, "add")
        self.assertEqual(self.client.post("/ozgur/compdocs/", payload).status_code, 403)
        existing_path = f"/ozgur/compdocs/{self.document.id}/"
        self.assertEqual(self.client.patch(existing_path, {"name": "Changed"}).status_code, 403)
        grant_model_permissions(self.user, CompDoc, "change")
        created = self.client.post("/ozgur/compdocs/", payload)
        self.assertEqual(created.status_code, 201)
        detail_path = f"/ozgur/compdocs/{created.data['id']}/"
        version = created.data["source_history_id"]
        updated = self.client.patch(
            detail_path, {"name": "Changed", "source_history_id": version}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.client.delete(detail_path).status_code, 403)

    def test_import_requires_add_and_change_permissions(self):
        """An upsert-capable workbook import requires both mutation permissions."""

        grant_model_permissions(self.user, CompDoc, "add")
        denied = self._preview_import()
        grant_model_permissions(self.user, CompDoc, "change")
        allowed = self._preview_import()

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)

    def test_bulk_delete_requires_permission_phrase_and_current_count(self):
        """Collection deletion is permissioned and bound to a reviewed row count."""

        payload = {"confirmation": "DELETE OZGUR COMPLIANCE DOCUMENTS", "expected_count": 1}
        self.assertEqual(self.client.delete("/ozgur/compdocs/", payload, format="json").status_code, 403)
        grant_model_permissions(self.user, CompDoc, "view", "delete")
        invalid = self.client.delete(
            "/ozgur/compdocs/", {**payload, "confirmation": "DELETE"}, format="json"
        )
        stale = self.client.delete(
            "/ozgur/compdocs/", {**payload, "expected_count": 2}, format="json"
        )
        deleted = self.client.delete("/ozgur/compdocs/", payload, format="json")

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "COMPDOC_DELETE_COUNT_CONFLICT")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(CompDoc.objects.exists())
        deletion = CompDoc.history.get(history_type="-")
        self.assertEqual(deletion.history_user, self.user)

    def _preview_import(self):
        return self.client.post(
            "/ozgur/compdocs/upload/?preview=true",
            {"file": workbook_upload([valid_row()])},
            format="multipart",
        )
