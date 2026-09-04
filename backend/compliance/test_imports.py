"""Preview/confirm import matching and concurrency acceptance tests."""

from datetime import date
from io import BytesIO

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.models import Panel, Project, ProjectRoleAssignment

from .models import ComplianceDocument, CoverPage, ImportAudit


class ComplianceImportTests(TestCase):
    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.user = get_user_model().objects.create_user("import-editor")
        ProjectRoleAssignment.objects.create(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.EDITOR,
            user=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.panel = Panel.objects.create(
            project=self.project,
            name="Flight Controls",
            ata="27-00",
        )

    def workbook(
        self,
        *,
        name="Imported Document",
        cover="CP-I",
        tech="TD-I",
        status=None,
        target_date=None,
        delivery_date=None,
        panel=None,
        ata=None,
    ):
        output = BytesIO()
        row = {
            "Document Name": name,
            "Cover Page Number": cover,
            "Technical Document No": tech,
        }
        if status is not None:
            row["Status"] = status
        if target_date is not None:
            row["UBM Target Date"] = target_date
        if delivery_date is not None:
            row["UBM Delivery Date"] = delivery_date
        if panel is not None:
            row["Panel"] = panel
        if ata is not None:
            row["ATA Chapter"] = ata
        pd.DataFrame([row]).to_excel(output, index=False)
        return output.getvalue()

    @staticmethod
    def upload(content):
        return SimpleUploadedFile(
            "compliance.xlsx",
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def preview(self, content):
        return self.client.post(
            "/api/projects/ozgur/compliance-documents/imports/preview/",
            {"file": self.upload(content)},
            format="multipart",
        )

    def confirm(self, content, token):
        return self.client.post(
            "/api/projects/ozgur/compliance-documents/imports/confirm/",
            {"file": self.upload(content), "confirmation_token": token},
            format="multipart",
        )

    def test_preview_then_confirm_creates_document_and_audit(self):
        content = self.workbook()
        preview = self.preview(content)
        confirmed = self.confirm(content, preview.data["confirmation_token"])

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["created_count"], 1)
        self.assertEqual(confirmed.status_code, 201)
        self.assertEqual(ComplianceDocument.objects.count(), 1)
        self.assertEqual(ImportAudit.objects.get().status, ImportAudit.Status.SUCCESS)

    def test_confirm_updates_existing_document_without_optional_panel(self):
        cover = CoverPage.objects.create(project=self.project, number="CP-I")
        document = ComplianceDocument.objects.create(
            project=self.project,
            cover_page=cover,
            name="Before import",
            tech_doc_no="TD-I",
            panel=None,
        )
        content = self.workbook()

        preview = self.preview(content)
        confirmed = self.confirm(content, preview.data["confirmation_token"])

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["updated_count"], 1)
        self.assertEqual(confirmed.status_code, 201)
        document.refresh_from_db()
        self.assertEqual(document.name, "Imported Document")
        self.assertIsNone(document.panel_id)

    def test_new_matching_target_after_preview_returns_version_conflict(self):
        content = self.workbook()
        preview = self.preview(content)
        cover = CoverPage.objects.create(project=self.project, number="CP-I")
        ComplianceDocument.objects.create(
            project=self.project,
            cover_page=cover,
            name="Imported Document",
            tech_doc_no="TD-I",
        )

        response = self.confirm(content, preview.data["confirmation_token"])

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "VERSION_CONFLICT")
        audit = ImportAudit.objects.get()
        self.assertEqual(audit.status, ImportAudit.Status.FAILED)
        self.assertEqual(audit.error_summary[0]["code"], "VERSION_CONFLICT")

    def test_import_matches_existing_document_by_name_when_technical_number_is_added(self):
        cover = CoverPage.objects.create(project=self.project, number="CP-I")
        document = ComplianceDocument.objects.create(
            project=self.project,
            cover_page=cover,
            name="Imported Document",
            tech_doc_no=None,
        )
        content = self.workbook()

        preview = self.preview(content)
        confirmed = self.confirm(content, preview.data["confirmation_token"])

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["updated_count"], 1)
        self.assertEqual(confirmed.status_code, 201)
        self.assertEqual(ComplianceDocument.objects.count(), 1)
        document.refresh_from_db()
        self.assertEqual(document.tech_doc_no, "TD-I")

    def test_workbook_change_after_preview_is_rejected(self):
        first = self.workbook(name="First")
        preview = self.preview(first)

        response = self.confirm(self.workbook(name="Second"), preview.data["confirmation_token"])

        self.assertEqual(response.status_code, 400)
        self.assertIn(response.data["code"], {"IMPORT_PREVIEW_MISMATCH", "VALIDATION_ERROR"})

    def test_import_resolves_flexibly_formatted_ata_column(self):
        for index, ata_value in enumerate((27, 2700, "27-00", "27.00", "ATA 27"), start=1):
            with self.subTest(ata_value=ata_value):
                content = self.workbook(
                    name=f"ATA document {index}",
                    cover=f"CP-ATA-{index}",
                    tech=f"TD-ATA-{index}",
                    ata=ata_value,
                )

                preview = self.preview(content)
                confirmed = self.confirm(content, preview.data["confirmation_token"])

                self.assertEqual(preview.status_code, 200)
                self.assertIn(
                    {"source": "ATA Chapter", "target": "ata"},
                    preview.data["mapped_columns"],
                )
                self.assertEqual(confirmed.status_code, 201)
                self.assertEqual(
                    ComplianceDocument.objects.get(name=f"ATA document {index}").panel,
                    self.panel,
                )

    def test_existing_panel_column_also_accepts_short_ata_format(self):
        content = self.workbook(panel=27)

        preview = self.preview(content)
        confirmed = self.confirm(content, preview.data["confirmation_token"])

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(confirmed.status_code, 201)
        self.assertEqual(ComplianceDocument.objects.get().panel, self.panel)

    def test_ata_disambiguates_a_panel_name_with_multiple_chapters(self):
        Panel.objects.create(
            project=self.project,
            name=self.panel.name,
            ata="28-00",
        )
        content = self.workbook(panel=self.panel.name, ata=27)

        preview = self.preview(content)
        confirmed = self.confirm(content, preview.data["confirmation_token"])

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(confirmed.status_code, 201)
        self.assertEqual(ComplianceDocument.objects.get().panel, self.panel)

    def test_conflicting_panel_and_ata_are_rejected(self):
        Panel.objects.create(
            project=self.project,
            name="Electrical",
            ata="24-00",
        )
        content = self.workbook(panel="Electrical", ata=27)

        preview = self.preview(content)

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["rejected_count"], 1)
        self.assertIn("ata", preview.data["invalid_documents"][0]["fields"])
        self.assertFalse(ComplianceDocument.objects.exists())

    def test_import_builds_to_be_issued_event_without_status_flow_column(self):
        content = self.workbook(
            status="To Be Issued",
            target_date=date(2026, 9, 10),
        )

        preview = self.preview(content)
        confirmed = self.confirm(content, preview.data["confirmation_token"])

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(confirmed.status_code, 201)
        document = ComplianceDocument.objects.get()
        event = document.workflow_events.get()
        self.assertEqual(document.status, "to_be_issued")
        self.assertEqual(document.ubm_target_date, date(2026, 9, 10))
        self.assertIsNone(document.ubm_delivery_date)
        self.assertEqual(
            (event.status, event.effective_date),
            ("to_be_issued", date(2026, 9, 10)),
        )

    def test_import_appends_current_status_with_ubm_delivery_date(self):
        initial = self.workbook(
            status="To Be Issued",
            target_date=date(2026, 9, 10),
        )
        initial_preview = self.preview(initial)
        self.confirm(initial, initial_preview.data["confirmation_token"])
        delivered = self.workbook(
            status="Authority Review",
            target_date=date(2026, 9, 10),
            delivery_date=date(2026, 9, 18),
        )

        preview = self.preview(delivered)
        confirmed = self.confirm(delivered, preview.data["confirmation_token"])

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["updated_count"], 1)
        self.assertEqual(confirmed.status_code, 201)
        document = ComplianceDocument.objects.get()
        events = list(
            document.workflow_events.order_by("sequence").values_list("status", "effective_date")
        )
        self.assertEqual(
            events,
            [
                ("to_be_issued", date(2026, 9, 10)),
                ("authority_review", date(2026, 9, 18)),
            ],
        )
        self.assertEqual(document.status, "authority_review")
        self.assertEqual(document.ubm_delivery_date, date(2026, 9, 18))

    def test_delivery_date_without_prior_target_is_rejected(self):
        response = self.preview(
            self.workbook(
                status="Authority Review",
                delivery_date=date(2026, 9, 18),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rejected_count"], 1)
        self.assertIn("ubm_delivery_date", response.data["invalid_documents"][0]["fields"])
