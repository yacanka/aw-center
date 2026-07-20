from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from projects.ozgur.models import CompDoc

from .compdoc_import_test_utils import (
    grant_model_permissions,
    valid_row,
    workbook_upload,
    workbook_upload_bytes,
)
from .models import CompDocImportAudit

User = get_user_model()


class CompDocImportAuditTests(TestCase):
    """Verify mapped upserts and permission-protected import evidence."""

    def setUp(self):
        """Create importer, audit viewer, and authenticated API client."""

        self.importer = User.objects.create_user("importer", password="StrongPass!123")
        self.viewer = User.objects.create_user("auditor", password="StrongPass!123")
        grant_model_permissions(self.importer, CompDoc, "add", "change")
        self.viewer.user_permissions.add(
            Permission.objects.get(codename="view_compdocimportaudit")
        )
        self.client = APIClient()
        self.client.force_authenticate(self.importer)

    def test_preview_maps_virtual_status_without_creating_audit(self):
        """Preview recognizes status and remains persistence-free."""

        response = self.client.post(
            "/ozgur/compdocs/upload/?preview=true",
            {"file": workbook_upload([valid_row()])},
            format="multipart",
        )

        targets = {mapping["target"] for mapping in response.data["mapped_columns"]}
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", targets)
        self.assertEqual(response.data["missing_columns"], [])
        self.assertEqual(response.data["created_count"], 1)
        self.assertTrue(response.data["confirmation_token"])
        self.assertIs(response.data["database_state_protected"], True)
        self.assertEqual(CompDocImportAudit.objects.count(), 0)

    def test_confirmed_import_creates_then_updates_by_cover_page_number(self):
        """Repeated business keys update one document and produce separate audits."""

        created = self.confirm([valid_row()])
        updated_row = valid_row(name="Updated Compliance Document")
        updated = self.confirm([updated_row])

        document = CompDoc.objects.get(cover_page_no="CP-001")
        self.assertEqual(created.data["created_count"], 1)
        self.assertEqual(updated.data["updated_count"], 1)
        self.assertEqual(CompDoc.objects.count(), 1)
        self.assertEqual(document.name, "Updated Compliance Document")
        self.assertEqual(CompDocImportAudit.objects.count(), 2)

    def test_no_op_import_persists_unchanged_audit_count(self):
        """Repeated identical content remains explicit without creating history writes."""

        self.confirm([valid_row()])
        response = self.confirm([valid_row()])
        audit = CompDocImportAudit.objects.get(pk=response.data["audit_id"])

        self.assertEqual(response.data["unchanged_count"], 1)
        self.assertEqual(audit.unchanged_count, 1)

    def test_partial_import_records_sanitized_row_failure(self):
        """A malformed row is rejected without rolling back valid evidence."""

        invalid_row = valid_row(name="Rejected", cover_page_no="CP-002")
        invalid_row["Status"] = ""
        response = self.confirm([valid_row(), invalid_row])
        audit = CompDocImportAudit.objects.get(pk=response.data["audit_id"])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_count"], 1)
        self.assertEqual(response.data["rejected_count"], 1)
        self.assertEqual(audit.status, CompDocImportAudit.Status.PARTIAL)
        self.assertEqual(audit.error_summary[0]["code"], "ROW_TRANSFORM_FAILED")
        self.assertNotIn("Traceback", str(audit.error_summary))

    def test_missing_columns_create_failed_audit(self):
        """Confirmed structurally invalid workbooks remain traceable."""

        response = self.confirm([{"Name": "Incomplete"}])
        audit = CompDocImportAudit.objects.get()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(audit.status, CompDocImportAudit.Status.FAILED)
        self.assertIn("cover_page_no", audit.missing_columns)
        self.assertEqual(len(audit.source_sha256), 64)

    @override_settings(AWCENTER_MAX_COMPDOC_IMPORT_ROWS=1)
    def test_row_limit_stops_work_during_persistence_free_preview(self):
        """Oversized workbooks fail before confirmation or database writes."""

        response = self.preview([valid_row(), valid_row(cover_page_no="CP-002")])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "COMPDOC_IMPORT_ROW_LIMIT")
        self.assertEqual(CompDocImportAudit.objects.count(), 0)
        self.assertEqual(CompDoc.objects.count(), 0)

    def test_audit_ledger_requires_permission_and_hides_digest_in_list(self):
        """Only explicit viewers can list compact evidence or inspect details."""

        import_response = self.confirm([valid_row()])
        denied = self.client.get("/projects/import-audits/")
        self.client.force_authenticate(self.viewer)
        listing = self.client.get("/projects/import-audits/?project=ozgur")
        detail = self.client.get(f"/projects/import-audits/{import_response.data['audit_id']}/")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn("source_sha256", listing.data["results"][0])
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["project_slug"], "ozgur")
        self.assertEqual(len(detail.data["source_sha256"]), 64)

    def test_unexpected_failure_is_audited_without_leaking_exception(self):
        """Unexpected parser failures expose only a stable support contract."""

        content, token = self.preview_content([valid_row()])
        with patch("common.compdoc_import_views.prepare_import") as prepare:
            prepare.side_effect = RuntimeError("private-workbook-value")
            with self.assertLogs("common.compdoc_import_views", level="ERROR"):
                response = self.confirm_content(content, token)
        audit = CompDocImportAudit.objects.get()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["code"], "COMPDOC_IMPORT_FAILED")
        self.assertEqual(audit.status, CompDocImportAudit.Status.FAILED)
        self.assertNotIn("private-workbook-value", str(response.data))
        self.assertNotIn("private-workbook-value", str(audit.error_summary))

    def confirm(self, rows):
        """Post one confirmed workbook import using a fresh upload stream."""

        content, token = self.preview_content(rows)
        return self.confirm_content(content, token)

    def preview(self, rows):
        """Post one persistence-free workbook preview."""

        return self.client.post(
            "/ozgur/compdocs/upload/?preview=true",
            {"file": workbook_upload(rows)},
            format="multipart",
        )

    def preview_content(self, rows):
        """Return exact workbook bytes and their signed preview confirmation."""

        upload = workbook_upload(rows)
        content = upload.read()
        response = self.client.post(
            "/ozgur/compdocs/upload/?preview=true",
            {"file": workbook_upload_bytes(content)},
            format="multipart",
        )
        return content, response.data["confirmation_token"]

    def confirm_content(self, content, token):
        """Confirm exact previewed bytes with their signed token."""

        return self.client.post(
            "/ozgur/compdocs/upload/?confirm_import=true",
            {"file": workbook_upload_bytes(content), "confirmation_token": token},
            format="multipart",
        )
