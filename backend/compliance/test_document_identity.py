"""Required cover/name identity and optional document metadata contracts."""
from io import BytesIO

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment
from .models import ComplianceDocument, CoverPage


class DocumentIdentityTests(TestCase):
    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.user = get_user_model().objects.create_user("identity-editor")
        ProjectRoleAssignment.objects.create(project=self.project, user=self.user,
                                            domain="compliance", role="editor")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = "/api/projects/ozgur/compliance-documents/"

    def create(self, name="Document", cover="CP-1", **extra):
        return self.client.post(self.base, {
            "name": name, "cover_page": {"number": cover}, **extra,
        }, format="json")

    def preview(self, rows):
        output = BytesIO()
        pd.DataFrame(rows).to_excel(output, index=False)
        self.content = output.getvalue()
        return self.client.post(self.base + "imports/preview/", {"file": self.upload()}, format="multipart")

    def upload(self):
        return SimpleUploadedFile("identity.xlsx", self.content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def confirm(self, preview):
        return self.client.post(self.base + "imports/confirm/", {
            "file": self.upload(), "confirmation_token": preview.data["confirmation_token"],
        }, format="multipart")

    def test_only_cover_number_and_name_are_required(self):
        accepted = self.create()
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertEqual(accepted.data["status"], "unknown")
        self.assertIsNone(accepted.data["panel"])
        self.assertIsNone(accepted.data["tech_doc_no"])
        fields = self.client.get(self.base + "fields/").data["fields"]
        self.assertEqual({field["key"] for field in fields if field["required"]}, {"name", "cover_page"})
        for blank in ("", "  ", None):
            self.assertEqual(self.create(name=blank, cover="CP-2").status_code, 400)
            self.assertEqual(self.create(name="Other", cover=blank).status_code, 400)
        for payload in ({"name": "Missing cover"}, {"name": "Missing number", "cover_page": {}}, {"cover_page": {"number": "CP-3"}}):
            self.assertEqual(self.client.post(self.base, payload, format="json").status_code, 400)

    def test_identity_is_a_project_scoped_pair_and_technical_numbers_may_repeat(self):
        self.assertEqual(self.create(tech_doc_no="TD-SHARED").status_code, 201)
        self.assertEqual(self.create(name="Other", tech_doc_no="TD-SHARED").status_code, 201)
        self.assertEqual(self.create(cover="CP-2", tech_doc_no="TD-SHARED").status_code, 201)
        duplicate = self.create()
        self.assertEqual(duplicate.status_code, 400, duplicate.data)
        other = Project.objects.get(slug="aesa")
        ProjectRoleAssignment.objects.create(project=other, user=self.user, domain="compliance", role="editor")
        response = self.client.post("/api/projects/aesa/compliance-documents/", {
            "name": "Document", "cover_page": {"number": "CP-1"},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_patch_cannot_clear_identity_or_create_duplicate_but_optional_patch_works(self):
        first = self.create().data
        second = self.create(name="Other").data
        url = self.base + second["id"] + "/"
        for payload in ({"name": " "}, {"cover_page": {"number": ""}}, {"name": first["name"]}):
            response = self.client.patch(url, {"version": 1, **payload}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        response = self.client.patch(url, {"version": 1, "notes": "Optional edit"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_model_validation_rejects_empty_identity(self):
        cover = CoverPage(project=self.project, number="")
        with self.assertRaises(ValidationError):
            cover.full_clean()
        legacy = CoverPage.objects.create(project=self.project, number="")
        document = ComplianceDocument(project=self.project, cover_page=legacy, name="Document")
        with self.assertRaises(ValidationError):
            document.full_clean()

    def test_import_requires_both_columns_and_rejects_blank_identity_rows(self):
        preview = self.preview([{"Document Name": "Document"}])
        self.assertEqual(preview.data["missing_columns"], ["cover_page_no"])
        self.assertEqual(preview.data["confirmation_token"], "")
        preview = self.preview([
            {"Document Name": "Valid", "Cover Page Number": "CP-1"},
            {"Document Name": "Blank", "Cover Page Number": " "},
            {"Document Name": " ", "Cover Page Number": "CP-2"},
        ])
        self.assertEqual(preview.data["created_count"], 1, preview.data)
        self.assertEqual(preview.data["rejected_count"], 2)
        self.assertEqual(self.confirm(preview).status_code, 201)
        self.assertEqual(ComplianceDocument.objects.count(), 1)

    def test_import_matches_only_cover_and_name_and_allows_shared_technical_number(self):
        self.create(name="Existing", tech_doc_no="TD-SHARED")
        preview = self.preview([
            {"Document Name": "New", "Cover Page Number": "CP-1", "Technical Document No": "TD-SHARED"},
            {"Document Name": "Existing", "Cover Page Number": "CP-1", "Technical Document No": "TD-UPDATED"},
        ])
        self.assertEqual(preview.data["created_count"], 1, preview.data)
        self.assertEqual(preview.data["updated_count"], 1, preview.data)
        self.assertEqual(self.confirm(preview).status_code, 201)
        self.assertEqual(ComplianceDocument.objects.count(), 2)
        self.assertEqual(ComplianceDocument.objects.get(name="Existing").tech_doc_no, "TD-UPDATED")
