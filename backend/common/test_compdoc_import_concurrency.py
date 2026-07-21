"""Regression tests for database-bound CompDoc import confirmations."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from projects.ozgur.models import CompDoc

from .compdoc_import_pipeline import save_row as persist_row
from .compdoc_import_test_utils import (
    grant_model_permissions,
    valid_row,
    workbook_upload,
    workbook_upload_bytes,
)
from .models import CompDocImportAudit

UPLOAD_URL = "/ozgur/compdocs/upload/"


class CompdocImportConcurrencyTests(TestCase):
    """Verify target changes invalidate previews and batch writes remain atomic."""

    def setUp(self):
        """Create one authorized importer and API client."""

        self.user = get_user_model().objects.create_user(
            "import-race-user", password="StrongPass!123"
        )
        grant_model_permissions(self.user, CompDoc, "add", "change")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_existing_target_change_rejects_without_overwrite(self):
        """A newer manual edit survives confirmation of an older workbook plan."""

        document = create_document("Before preview")
        content, token = self.preview([valid_row(name="Workbook update")])
        document.name = "Concurrent manual update"
        document.save(update_fields=["name"])

        response = self.confirm(content, token)

        document.refresh_from_db()
        self.assert_conflict(response)
        self.assertEqual(document.name, "Concurrent manual update")

    def test_target_create_and_delete_each_invalidate_preview(self):
        """Absent-to-present and present-to-absent transitions cannot change action semantics."""

        create_content, create_token = self.preview([valid_row()])
        created = create_document("Created after preview")
        create_conflict = self.confirm(create_content, create_token)
        created.delete()
        delete_content, delete_token = self.preview([valid_row()])
        recreated = create_document("Recreated after preview")
        recreated.delete()
        delete_conflict = self.confirm(delete_content, delete_token)

        self.assert_conflict(create_conflict)
        self.assert_conflict(delete_conflict)
        self.assertFalse(CompDoc.objects.exists())

    def test_unrelated_document_change_does_not_invalidate_plan(self):
        """Database proof is scoped to workbook business keys instead of the whole project."""

        target = create_document("Target before preview")
        unrelated = CompDoc.objects.create(name="Other", cover_page_no="CP-999")
        content, token = self.preview([valid_row(name="Target from workbook")])
        unrelated.name = "Unrelated concurrent update"
        unrelated.save(update_fields=["name"])

        response = self.confirm(content, token)

        target.refresh_from_db()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(target.name, "Target from workbook")

    def test_unexpected_second_write_rolls_back_entire_batch(self):
        """A persistence failure cannot leave a partially applied valid batch."""

        rows = [valid_row(), valid_row(cover_page_no="CP-002")]
        content, token = self.preview(rows)
        call_count = 0

        def fail_second_write(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("simulated write failure")
            return persist_row(*args)

        with patch("common.compdoc_import_pipeline.save_row", side_effect=fail_second_write):
            with self.assertLogs("common.compdoc_import_views", level="ERROR"):
                response = self.confirm(content, token)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(CompDoc.objects.exists())
        self.assertEqual(CompDocImportAudit.objects.get().status, "failed")

    def preview(self, rows):
        """Return exact workbook bytes and their database-bound confirmation token."""

        upload = workbook_upload(rows)
        content = upload.read()
        response = self.client.post(
            f"{UPLOAD_URL}?preview=true",
            {"file": workbook_upload_bytes(content)},
            format="multipart",
        )
        return content, response.data["confirmation_token"]

    def confirm(self, content, token):
        """Confirm the exact workbook against its reviewed database state."""

        return self.client.post(
            f"{UPLOAD_URL}?confirm_import=true",
            {"file": workbook_upload_bytes(content), "confirmation_token": token},
            format="multipart",
        )

    def assert_conflict(self, response):
        """Assert the stable database-state conflict contract."""

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "COMPDOC_IMPORT_DATABASE_CONFLICT")


def create_document(name):
    """Create one import target using the representative workbook business key."""

    return CompDoc.objects.create(name=name, cover_page_no="CP-001", tech_doc_no="TD-001")
