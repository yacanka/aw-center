"""Acceptance tests for verified DOORS module compliance imports."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from jobs.models import Job, JobStatus
from orgs.models import Project, ProjectRoleAssignment

from .models import ComplianceDocument, DoorsImportMapping, ImportAudit


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
                {"Document Title": "Invalid", "Cover Code": ""},
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

    def export_job(self, rows, *, truncated=False):
        columns = list(rows[0])
        payload = {
            "type": "doors_module_export",
            "schema_version": 1,
            "module_path": "/Project/Compliance",
            "columns": columns,
            "count": len(rows),
            "truncated": truncated,
            "attributes_truncated": False,
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
