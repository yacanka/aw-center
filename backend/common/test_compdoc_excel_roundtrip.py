"""End-to-end tests for the generated CompDoc export/import contract."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from common.compdoc_excel_export import build_excel_response
from common.compdoc_import_test_utils import grant_model_permissions, workbook_upload_bytes
from projects.ozgur.models import CompDoc
from projects.ozgur.serializers import CompDocSerializer


class CompDocExcelRoundTripTests(TestCase):
    """Prove a generated workbook can pass the live preview and confirmation flow."""

    def setUp(self):
        """Create one editable document and an authorized importer."""

        self.user = get_user_model().objects.create_user("roundtrip-user")
        grant_model_permissions(self.user, CompDoc, "add", "change")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.document = CompDoc.objects.create(
            name="Unscheduled Manual",
            cover_page_no="CP-ROUNDTRIP",
            ata="21-00",
        )

    def test_generated_export_confirms_without_changing_the_document(self):
        """The dashboard export is accepted as an unchanged first-sheet import."""

        content = build_excel_response(CompDoc, CompDocSerializer).content
        preview = self.preview(content)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["missing_columns"], [])
        self.assertEqual(preview.data["rejected_count"], 0)
        self.assertEqual(preview.data["unchanged_count"], 1)

        confirmed = self.confirm(content, preview.data["confirmation_token"])
        self.assertEqual(confirmed.status_code, 201)
        self.assertEqual(confirmed.data["unchanged_count"], 1)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status_flow, [])

    def preview(self, content):
        """Submit generated workbook bytes to the production preview path."""

        return self.client.post(
            "/ozgur/compdocs/upload/?preview=true",
            {"file": workbook_upload_bytes(content)},
            format="multipart",
        )

    def confirm(self, content, confirmation_token):
        """Confirm the exact workbook bytes reviewed by the preview."""

        return self.client.post(
            "/ozgur/compdocs/upload/?confirm_import=true",
            {
                "file": workbook_upload_bytes(content),
                "confirmation_token": confirmation_token,
            },
            format="multipart",
        )
