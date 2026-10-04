"""Acceptance tests for verified DOORS module compliance imports."""

import hashlib
import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from jobs.models import Job, JobStatus
from orgs.models import Panel, Project, ProjectRoleAssignment

from .models import ComplianceDocument, CoverPage, DoorsImportMapping, ImportAudit, WorkflowEvent


class ComplianceDoorsImportTests(TestCase):
    def setUp(self):
        self.media_directory = Path(tempfile.mkdtemp())
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory / "public",
            PRIVATE_MEDIA_ROOT=self.media_directory / "private",
        )
        self.settings_override.enable()
        self.project = Project.objects.get(slug="ozgur")
        self.user = get_user_model().objects.create_user("doors-import-editor")
        ProjectRoleAssignment.objects.create(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.EDITOR,
            user=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_directory, ignore_errors=True)

    def test_preview_confirm_uses_shared_validation_and_saves_successful_mapping(self):
        job = self.export_job(
            [
                {
                    "Document Title": "DOORS Document",
                    "Cover Code": "CP-D",
                    "Technical Number": "TD-D",
                }
            ]
        )
        mapping = {
            "Document Title": "name",
            "Cover Code": "cover_page_no",
            "Technical Number": "tech_doc_no",
        }

        preview = self.client.post(self.preview_url(), {"job_id": job.pk, "mapping": mapping}, format="json")
        confirmed = self.client.post(
            self.confirm_url(),
            {
                "job_id": job.pk,
                "mapping": mapping,
                "confirmation_token": preview.data["confirmation_token"],
            },
            format="json",
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["created_count"], 1)
        self.assertEqual(confirmed.status_code, 201)
        document = ComplianceDocument.objects.get()
        self.assertEqual(document.name, "DOORS Document")
        self.assertEqual(document.cover_page.number, "CP-D")
        self.assertEqual(document.tech_doc_no, "TD-D")
        self.assertEqual(ImportAudit.objects.get().status, ImportAudit.Status.SUCCESS)
        saved = DoorsImportMapping.objects.get(project=self.project)
        self.assertEqual(saved.module_path, "/Project/Compliance")
        self.assertEqual(saved.mapping, mapping)

        source = self.client.get(self.source_url(job))
        self.assertEqual(source.status_code, 200)
        self.assertEqual(source.data["default_mapping"], mapping)

    def test_iso_export_dates_survive_preview_confirmation_independently(self):
        job = self.export_job([
            {"Title": "Dated", "Cover": "CP-D", "Target": "2028-02-29", "Revised": "2028-03-15", "Delivery": "2028-02-01", "Effective": "", "Status": ""},
            {"Title": "Undated", "Cover": "CP-D", "Target": "", "Delivery": None, "Effective": "", "Status": ""},
            {"Title": "01 October 2026 Thursday", "Cover": "CP-D", "Target": "", "Delivery": "", "Effective": "2026-10-01", "Status": "To Be Issued"},
        ])
        mapping = {
            "Title": "name", "Cover": "cover_page_no", "Target": "ubm_target_date",
            "Revised": "ubm_revised_target_date", "Delivery": "ubm_delivery_date", "Effective": "effective_date", "Status": "status",
        }
        values = {"job_id": job.pk, "mapping": mapping}
        preview = self.client.post(self.preview_url(), values, format="json")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["created_count"], 3)
        self.assertEqual(preview.data["rejected_count"], 0)
        confirmed = self.client.post(self.confirm_url(), {
            **values, "confirmation_token": preview.data["confirmation_token"],
        }, format="json")
        self.assertEqual(confirmed.status_code, 201)
        document = ComplianceDocument.objects.get(name="Dated")
        self.assertEqual(document.ubm_target_date, date(2028, 2, 29))
        self.assertEqual(document.ubm_revised_target_date, date(2028, 3, 15))
        self.assertEqual(document.ubm_delivery_date, date(2028, 2, 1))
        self.assertEqual(
            list(document.workflow_events.order_by("sequence").values_list("effective_date", flat=True)),
            [],
        )
        undated = ComplianceDocument.objects.get(name="Undated")
        self.assertIsNone(undated.ubm_target_date)
        self.assertIsNone(undated.ubm_delivery_date)
        effective = ComplianceDocument.objects.get(name="01 October 2026 Thursday")
        self.assertEqual(effective.workflow_events.get().effective_date, date(2026, 10, 1))

    def test_invalid_export_date_is_rejected_with_doors_object_context(self):
        job = self.export_job([{"Title": "Invalid date", "Cover": "CP-D", "Target": "2026-02-29"}])
        preview = self.client.post(self.preview_url(), {
            "job_id": job.pk,
            "mapping": {"Title": "name", "Cover": "cover_page_no", "Target": "ubm_target_date"},
        }, format="json")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["rejected_count"], 1)
        error = preview.data["invalid_documents"][0]
        self.assertIn("ubm_target_date", error["fields"])
        self.assertEqual(error["doors_object"], {"absolute_number": 1, "identifier": "REQ-1"})
        self.assertFalse(ComplianceDocument.objects.exists())

    def test_explicit_out_of_order_transition_is_rejected_in_doors_preview(self):
        cover = CoverPage.objects.create(project=self.project, number="CP-D")
        document = ComplianceDocument.objects.create(
            project=self.project, cover_page=cover, name="Existing", status="to_be_issued",
        )
        WorkflowEvent.objects.create(
            document=document, sequence=1, status="to_be_issued",
            effective_date=date(2028, 9, 20), source=WorkflowEvent.Source.IMPORT,
        )
        job = self.export_job([{
            "Title": "Existing", "Cover": "CP-D", "Status": "Authority Review",
            "Effective": "2028-09-10", "Delivery": "2028-09-01",
        }])
        preview = self.client.post(self.preview_url(), {
            "job_id": job.pk,
            "mapping": {
                "Title": "name", "Cover": "cover_page_no", "Status": "status",
                "Effective": "effective_date", "Delivery": "ubm_delivery_date",
            },
        }, format="json")

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["rejected_count"], 1)
        self.assertIn("effective_date", preview.data["invalid_documents"][0]["fields"])

    def test_doors_import_creates_and_renames_project_panels(self):
        existing = Panel.objects.create(project=self.project, ata="27-00", name="Old")
        job = self.export_job([
            {"Title": "First", "Cover": "CP-P", "Panel": "New", "ATA": "29"},
            {"Title": "Second", "Cover": "CP-P", "Panel": "Renamed", "ATA": "27"},
        ])
        values = {"job_id": job.pk, "mapping": {"Title": "name", "Cover": "cover_page_no", "Panel": "panel", "ATA": "ata"}}
        preview = self.client.post(self.preview_url(), values, format="json")
        self.assertEqual(preview.data["created_count"], 2)
        self.assertEqual(len(preview.data["panel_changes"]), 2)
        self.assertFalse(Panel.objects.filter(project=self.project, ata="29-00").exists())
        response = self.client.post(self.confirm_url(), {
            **values, "confirmation_token": preview.data["confirmation_token"],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        existing.refresh_from_db()
        self.assertEqual(existing.name, "Renamed")
        self.assertEqual(ComplianceDocument.objects.get(name="Second").panel, existing)
        self.assertEqual(ComplianceDocument.objects.get(name="First").panel.ata, "29-00")

    def test_confirmation_is_bound_to_reviewed_mapping(self):
        job = self.export_job(
            [{"Document Title": "DOORS Document", "Cover Code": "CP-D"}]
        )
        mapping = {"Document Title": "name", "Cover Code": "cover_page_no"}
        preview = self.client.post(self.preview_url(), {"job_id": job.pk, "mapping": mapping}, format="json")

        response = self.client.post(
            self.confirm_url(),
            {
                "job_id": job.pk,
                "mapping": {"Document Title": "cover_page_no", "Cover Code": "name"},
                "confirmation_token": preview.data["confirmation_token"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(response.data["code"], {"IMPORT_PREVIEW_MISMATCH", "VALIDATION_ERROR"})
        self.assertFalse(ComplianceDocument.objects.exists())

    def test_source_reports_real_values_and_canonical_required_fields(self):
        job = self.export_job([
            {" Başlık ": "Document", "Count": 0, "Empty": " \t"},
            {" Başlık ": "", "Count": False, "Empty": None},
        ])

        response = self.client.get(self.source_url(job))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["columns"], [" Başlık ", "Count", "Empty"])
        self.assertEqual(response.data["column_summaries"], {
            " Başlık ": {"populated_count": 1, "examples": ["Document"]},
            "Count": {"populated_count": 2, "examples": ["0", "False"]},
            "Empty": {"populated_count": 0, "examples": []},
        })
        self.assertEqual(
            [field["key"] for field in response.data["target_fields"] if field["required"]],
            ["cover_page_no", "name"],
        )

    def test_exact_attribute_mapping_reports_the_empty_object_only(self):
        job = self.export_job([
            {" Başlık ": "Document", "Başlık": "", "Cover": "CP-D"},
            {" Başlık ": " \t", "Başlık": "Other attribute is populated", "Cover": "CP-D"},
        ])

        response = self.client.post(self.preview_url(), {
            "job_id": job.pk, "mapping": {" Başlık ": "name", "Cover": "cover_page_no"},
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created_count"], 1)
        self.assertEqual(response.data["rejected_count"], 1)
        error = response.data["invalid_documents"][0]
        self.assertEqual(error["row"], 2)
        self.assertEqual(error["doors_object"], {"absolute_number": 2, "identifier": "REQ-2"})
        self.assertIn("name", error["fields"])

    def test_zero_attribute_is_preserved_through_preview_and_confirmation(self):
        job = self.export_job([{"Title": 0, "Cover": 0}])
        mapping = {"Title": "name", "Cover": "cover_page_no"}
        preview = self.client.post(self.preview_url(), {
            "job_id": job.pk, "mapping": mapping,
        }, format="json")

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["created_count"], 1)
        self.assertEqual(preview.data["rejected_count"], 0)
        response = self.client.post(self.confirm_url(), {
            "job_id": job.pk, "mapping": mapping,
            "confirmation_token": preview.data["confirmation_token"],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        document = ComplianceDocument.objects.get()
        self.assertEqual(document.name, "0")
        self.assertEqual(document.cover_page.number, "0")

    def test_partial_import_does_not_replace_last_successful_mapping(self):
        previous = DoorsImportMapping.objects.create(
            project=self.project,
            module_path="/Project/Compliance",
            mapping={"Old Name": "name", "Old Cover": "cover_page_no"},
            source_columns=["Old Name", "Old Cover"],
            updated_by=self.user,
            successful_at="2026-01-01T00:00:00Z",
        )
        job = self.export_job(
            [
                {"Document Title": "Valid", "Cover Code": "CP-1"},
                {"Document Title": "", "Cover Code": "CP-INVALID"},
            ]
        )
        mapping = {"Document Title": "name", "Cover Code": "cover_page_no"}
        preview = self.client.post(self.preview_url(), {"job_id": job.pk, "mapping": mapping}, format="json")
        response = self.client.post(
            self.confirm_url(),
            {
                "job_id": job.pk,
                "mapping": mapping,
                "confirmation_token": preview.data["confirmation_token"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], ImportAudit.Status.PARTIAL)
        previous.refresh_from_db()
        self.assertEqual(previous.mapping, {"Old Name": "name", "Old Cover": "cover_page_no"})

    def test_source_is_owner_scoped(self):
        job = self.export_job([{"Document Title": "Doc", "Cover Code": "CP"}])
        other_user = get_user_model().objects.create_user("other-doors-importer")
        ProjectRoleAssignment.objects.create(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.EDITOR,
            user=other_user,
        )
        self.client.force_authenticate(other_user)

        response = self.client.get(self.source_url(job))

        self.assertEqual(response.status_code, 404)

    def test_truncated_module_export_is_rejected_instead_of_partially_imported(self):
        job = self.export_job(
            [{"Document Title": "Doc", "Cover Code": "CP"}],
            truncated=True,
        )

        response = self.client.get(self.source_url(job))

        self.assertEqual(response.status_code, 400)
        self.assertIn(response.data["code"], {"IMPORT_ROW_LIMIT", "VALIDATION_ERROR"})
        self.assertFalse(ComplianceDocument.objects.exists())

    @override_settings(MAX_DOORS_COLUMNS=250)
    def test_source_accepts_configured_column_limit_and_rejects_overflow(self):
        for count, expected_status in ((250, 200), (251, 400)):
            with self.subTest(columns=count):
                job = self.export_job([{f"Field {index}": "value" for index in range(count)}])
                response = self.client.get(self.source_url(job))
                self.assertEqual(response.status_code, expected_status)

    @override_settings(MAX_DOORS_COLUMNS=2)
    def test_source_enforces_lower_configured_column_limit(self):
        job = self.export_job([{"Title": "Doc", "Cover": "CP", "Extra": "value"}])
        self.assertEqual(self.client.get(self.source_url(job)).status_code, 400)

    @override_settings(MAX_DOORS_COLUMNS=250)
    def test_attribute_truncation_is_rejected_with_configured_limit(self):
        job = self.export_job([{"Title": "Doc"}], attributes_truncated=True)
        response = self.client.get(self.source_url(job))
        self.assertEqual(response.status_code, 400)
        self.assertIn("250-field", str(response.data))
        self.assertFalse(ComplianceDocument.objects.exists())

    def export_job(self, rows, *, truncated=False, attributes_truncated=False):
        columns = list(rows[0])
        payload = {
            "type": "doors_module_export",
            "schema_version": 1,
            "module_path": "/Project/Compliance",
            "columns": columns,
            "count": len(rows),
            "truncated": truncated,
            "attributes_truncated": attributes_truncated,
            "results": [
                {
                    "absolute_number": index,
                    "identifier": f"REQ-{index}",
                    "level": 1,
                    "attributes": row,
                }
                for index, row in enumerate(rows, start=1)
            ],
        }
        encoded = json.dumps(payload).encode()
        job = Job.objects.create(
            owner=self.user,
            kind="doors.run_dxl",
            title="Export DOORS module for compliance import",
            status=JobStatus.SUCCEEDED,
            progress=100,
            input_file=SimpleUploadedFile("doors-operation.json", b"{}"),
            input_name="doors-operation.json",
            input_sha256=hashlib.sha256(b"{}").hexdigest(),
            output_name="doors-result.json",
            output_sha256=hashlib.sha256(encoded).hexdigest(),
        )
        job.output_file.save("doors-result.json", ContentFile(encoded), save=True)
        return job

    @staticmethod
    def source_url(job):
        return f"/api/projects/ozgur/compliance-documents/imports/doors/sources/{job.pk}/"

    @staticmethod
    def preview_url():
        return "/api/projects/ozgur/compliance-documents/imports/doors/preview/"

    @staticmethod
    def confirm_url():
        return "/api/projects/ozgur/compliance-documents/imports/doors/confirm/"
