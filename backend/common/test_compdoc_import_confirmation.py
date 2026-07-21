from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from projects.ozgur.models import CompDoc
from projects.piku.models import CompDoc as PikuCompDoc

from .compdoc_import_test_utils import (
    grant_model_permissions,
    valid_row,
    workbook_upload,
    workbook_upload_bytes,
)
from .models import CompDocImportAudit

User = get_user_model()
UPLOAD_URL = "/ozgur/compdocs/upload/"


class CompDocImportConfirmationTests(TestCase):
    """Verify exact-file confirmation and actionable import impact planning."""

    def setUp(self):
        """Create two authenticated users and one API client."""

        self.user = User.objects.create_user("previewer", password="StrongPass!123")
        self.other_user = User.objects.create_user("other-preview", password="StrongPass!123")
        grant_model_permissions(self.user, CompDoc, "add", "change")
        grant_model_permissions(self.user, PikuCompDoc, "add", "change")
        grant_model_permissions(self.other_user, CompDoc, "add", "change")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_direct_confirmation_without_preview_is_rejected(self):
        """A query flag alone cannot authorize bulk persistence."""

        response = self.confirm(workbook_upload([valid_row()]), "")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "COMPDOC_IMPORT_CONFIRMATION_REQUIRED")
        self.assertEqual(CompDoc.objects.count(), 0)
        self.assertEqual(CompDocImportAudit.objects.count(), 0)

    def test_confirmation_is_bound_to_exact_workbook_bytes(self):
        """A token for one workbook cannot confirm a changed workbook."""

        _, preview = self.preview([valid_row()])
        changed = workbook_upload([valid_row(name="Unreviewed replacement")])

        response = self.confirm(changed, preview.data["confirmation_token"])

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "COMPDOC_IMPORT_PREVIEW_MISMATCH")
        self.assertEqual(CompDoc.objects.count(), 0)

    def test_confirmation_is_bound_to_previewing_user(self):
        """Another authenticated user cannot reuse a preview decision."""

        content, preview = self.preview([valid_row()])
        self.client.force_authenticate(self.other_user)

        response = self.confirm(workbook_upload_bytes(content), preview.data["confirmation_token"])

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "COMPDOC_IMPORT_PREVIEW_MISMATCH")

    def test_confirmation_is_bound_to_previewed_project(self):
        """A workbook reviewed for one project cannot mutate another project."""

        content, preview = self.preview([valid_row()])
        response = self.client.post(
            "/piku/compdocs/upload/?confirm_import=true",
            {
                "file": workbook_upload_bytes(content),
                "confirmation_token": preview.data["confirmation_token"],
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "COMPDOC_IMPORT_PREVIEW_MISMATCH")

    def test_invalid_confirmation_is_rejected(self):
        """Invalid signatures expose one stable, actionable error."""

        response = self.confirm(workbook_upload([valid_row()]), "invalid-token")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "COMPDOC_IMPORT_PREVIEW_EXPIRED")

    @override_settings(COMPDOC_IMPORT_PREVIEW_TTL_SECONDS=1)
    def test_expired_confirmation_is_rejected(self):
        """A valid decision cannot be applied after its bounded lifetime."""

        upload = workbook_upload([valid_row()])
        content = upload.read()
        with patch("django.core.signing.time.time", return_value=1000):
            preview = self.client.post(
                f"{UPLOAD_URL}?preview=true",
                {"file": workbook_upload_bytes(content)},
                format="multipart",
            )
        with patch("django.core.signing.time.time", return_value=1002):
            response = self.confirm(
                workbook_upload_bytes(content), preview.data["confirmation_token"]
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "COMPDOC_IMPORT_PREVIEW_EXPIRED")

    def test_preview_reports_create_update_and_unchanged_impact(self):
        """The plan distinguishes actual writes from no-op rows."""

        content, initial = self.preview([valid_row()])
        self.confirm(workbook_upload_bytes(content), initial.data["confirmation_token"])
        unchanged_content, unchanged = self.preview([valid_row()])
        _, updated = self.preview([valid_row(name="Changed")])

        self.assertEqual(unchanged.data["unchanged_count"], 1)
        self.assertEqual(unchanged.data["updated_count"], 0)
        self.assertEqual(updated.data["updated_count"], 1)
        history_count = CompDoc.objects.get().history.count()
        result = self.confirm(
            workbook_upload_bytes(unchanged_content), unchanged.data["confirmation_token"]
        )
        self.assertEqual(result.data["unchanged_count"], 1)
        self.assertEqual(CompDoc.objects.get().history.count(), history_count)

    def test_duplicate_business_keys_are_rejected_before_writes(self):
        """Ambiguous duplicate cover-page numbers never become order-dependent writes."""

        rows = [valid_row(), valid_row(name="Duplicate")]
        _, preview = self.preview(rows)

        self.assertEqual(preview.data["rejected_count"], 2)
        self.assertEqual(
            {item["code"] for item in preview.data["invalid_documents"]},
            {"ROW_DUPLICATE_KEY"},
        )

    def test_one_cover_page_can_import_multiple_compliance_documents(self):
        """Distinct technical documents under one cover page are planned independently."""

        second = valid_row(name="Second Compliance Document")
        second["Tech Doc No"] = "TD-002"
        content, preview = self.preview([valid_row(), second])

        self.assertEqual(preview.data["created_count"], 2)
        self.assertEqual(preview.data["rejected_count"], 0)
        response = self.confirm(
            workbook_upload_bytes(content), preview.data["confirmation_token"]
        )
        documents = list(CompDoc.objects.order_by("name"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0].cover_page_id, documents[1].cover_page_id)

    def preview(self, rows):
        """Return exact workbook bytes and preview response."""

        upload = workbook_upload(rows)
        content = upload.read()
        response = self.client.post(
            f"{UPLOAD_URL}?preview=true",
            {"file": workbook_upload_bytes(content)},
            format="multipart",
        )
        return content, response

    def confirm(self, upload, token):
        """Submit an exact-file confirmation request."""

        return self.client.post(
            f"{UPLOAD_URL}?confirm_import=true",
            {"file": upload, "confirmation_token": token},
            format="multipart",
        )
