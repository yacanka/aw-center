"""Named ATA-less panels retain independent document assignments."""

from io import BytesIO
from unittest.mock import patch

import pandas as pd
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from orgs.models import Panel, Person, Project, ProjectRoleAssignment, ResponsibleAssignment
from orgs.serializers import PanelSerializer

from .models import ComplianceDocument, CoverPage
from . import test_imports as import_helpers


class OptionalAtaTests(TestCase):
    setUp = import_helpers.ComplianceImportTests.setUp
    upload = staticmethod(import_helpers.ComplianceImportTests.upload)
    preview = import_helpers.ComplianceImportTests.preview
    confirm = import_helpers.ComplianceImportTests.confirm

    def workbook(self, rows):
        output = BytesIO()
        pd.DataFrame(rows).to_excel(output, index=False)
        return output.getvalue()

    def import_rows(self, rows):
        content = self.workbook(rows)
        preview = self.preview(content)
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["rejected_count"], 0, preview.data)
        confirmed = self.confirm(content, preview.data["confirmation_token"])
        self.assertEqual(confirmed.status_code, 201, confirmed.data)
        return content, preview

    def test_repeated_names_and_different_empty_names_create_only_distinct_panels(self):
        rows = [
            {"name": "A", "cover_page_no": "CP", "panel": "Straße"},
            {"name": "B", "cover_page_no": "CP", "panel": " STRASSE "},
            {"name": "C", "cover_page_no": "CP", "panel": "Structures"},
        ]
        content = self.workbook(rows)
        preview = self.preview(content)
        self.assertEqual(preview.data["rejected_count"], 0, preview.data)
        self.assertEqual(len(preview.data["panel_changes"]), 2)
        self.assertEqual(Panel.objects.filter(project=self.project, ata="").count(), 0)
        self.assertEqual(self.confirm(content, preview.data["confirmation_token"]).status_code, 201)
        documents = {doc.name: doc for doc in ComplianceDocument.objects.select_related("panel")}
        self.assertEqual(documents["A"].panel_id, documents["B"].panel_id)
        self.assertNotEqual(documents["A"].panel_id, documents["C"].panel_id)
        self.assertEqual(documents["A"].panel.ata, "")
        self.assertEqual(self.preview(content).data["unchanged_count"], 3)

    def test_missing_ata_never_infers_populated_chapters(self):
        Panel.objects.create(project=self.project, name=self.panel.name, ata="28-00")
        self.import_rows([
            {"name": "Empty", "cover_page_no": "CP", "panel": self.panel.name, "ata": None},
            {"name": "First", "cover_page_no": "CP", "panel": self.panel.name, "ata": 27},
            {"name": "Second", "cover_page_no": "CP", "panel": self.panel.name, "ata": 28},
        ])
        self.assertEqual(ComplianceDocument.objects.get(name="Empty").panel.ata, "")
        self.assertEqual(ComplianceDocument.objects.get(name="First").panel.ata, "27-00")
        self.assertEqual(ComplianceDocument.objects.get(name="Second").panel.ata, "28-00")

    def test_missing_ata_does_not_infer_even_a_single_populated_panel(self):
        self.import_rows([{"name": "A", "cover_page_no": "CP", "panel": self.panel.name}])
        self.assertEqual(ComplianceDocument.objects.get().panel.ata, "")

    def test_numeric_panel_names_do_not_infer_ata_when_column_is_missing(self):
        self.import_rows([{"name": "A", "cover_page_no": "CP", "panel": "27"}])
        document = ComplianceDocument.objects.get()
        self.assertEqual(document.panel.name, "27")
        self.assertEqual(document.panel.ata, "")

    def test_blank_ata_without_panel_column_preserves_existing_panel_name(self):
        cover = CoverPage.objects.create(project=self.project, number="CP")
        document = ComplianceDocument.objects.create(
            project=self.project, cover_page=cover, name="A", panel=self.panel,
        )
        self.import_rows([{"name": "A", "cover_page_no": "CP", "ata": None}])
        document.refresh_from_db()
        self.assertIsNotNone(document.panel)
        self.assertEqual(document.panel.name, self.panel.name)
        self.assertEqual(document.panel.ata, "")

    def test_omitted_ata_preserves_existing_reference_but_blank_cell_clears_only_ata(self):
        cover = CoverPage.objects.create(project=self.project, number="CP")
        document = ComplianceDocument.objects.create(
            project=self.project, cover_page=cover, name="A", panel=self.panel,
        )
        self.import_rows([{"name": "A", "cover_page_no": "CP", "panel": self.panel.name}])
        document.refresh_from_db()
        self.assertEqual(document.panel_id, self.panel.pk)
        self.import_rows([{"name": "A", "cover_page_no": "CP", "panel": self.panel.name, "ata": None}])
        document.refresh_from_db()
        self.assertEqual(document.panel.name, self.panel.name)
        self.assertEqual(document.panel.ata, "")
        self.panel.refresh_from_db()
        self.assertEqual(self.panel.ata, "27-00")

    def test_assigning_ata_to_one_document_does_not_change_shared_empty_panel(self):
        self.import_rows([
            {"name": "A", "cover_page_no": "CP", "panel": self.panel.name},
            {"name": "B", "cover_page_no": "CP", "panel": self.panel.name},
        ])
        sibling = ComplianceDocument.objects.get(name="B")
        empty_panel_id = sibling.panel_id
        self.import_rows([{"name": "A", "cover_page_no": "CP", "panel": self.panel.name, "ata": 27}])
        sibling.refresh_from_db()
        self.assertEqual(sibling.panel_id, empty_panel_id)
        self.assertEqual(sibling.panel.ata, "")
        self.assertEqual(ComplianceDocument.objects.get(name="A").panel_id, self.panel.pk)

    def test_invalid_rows_do_not_create_panels_and_document_failure_rolls_back(self):
        content = self.workbook([
            {"name": "Valid", "cover_page_no": "CP", "panel": "Accepted"},
            {"name": "Invalid", "cover_page_no": "CP", "panel": "Rejected", "notes": "x" * 5001},
        ])
        preview = self.preview(content)
        self.assertEqual(preview.data["created_count"], 1, preview.data)
        self.assertEqual(preview.data["rejected_count"], 1)
        self.assertEqual([change["new_name"] for change in preview.data["panel_changes"]], ["Accepted"])
        with patch("compliance.imports.ComplianceDocumentSerializer.create", side_effect=ValidationError("Failure")):
            response = self.confirm(content, preview.data["confirmation_token"])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Panel.objects.filter(project=self.project, ata="").exists())

    def test_concurrent_empty_panel_creation_invalidates_preview(self):
        content = self.workbook([{"name": "A", "cover_page_no": "CP", "panel": "New"}])
        preview = self.preview(content)
        Panel.objects.create(project=self.project, name="New", ata="")
        response = self.confirm(content, preview.data["confirmation_token"])
        self.assertEqual(response.status_code, 409, response.data)
        self.assertFalse(ComplianceDocument.objects.exists())

    def test_database_enforces_unicode_normalized_empty_name_uniqueness_per_project(self):
        Panel.objects.create(project=self.project, name="Straße", ata="")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Panel.objects.create(project=self.project, name=" STRASSE ", ata="")
        Panel.objects.create(project=self.project, name="Other", ata="")
        Panel.objects.create(project=Project.objects.get(slug="aesa"), name="Straße", ata="")
        self.assertEqual(Panel.objects.filter(ata="").count(), 3)

    def test_panel_serializer_accepts_empty_ata_and_rejects_duplicate_name(self):
        serializer = PanelSerializer(data={"name": "New"}, context={"project": self.project})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        panel = serializer.save(project=self.project)
        self.assertEqual(panel.ata, "")
        duplicate = PanelSerializer(data={"name": " NEW ", "ata": ""}, context={"project": self.project})
        self.assertFalse(duplicate.is_valid())
        self.assertIn("name", duplicate.errors)

    def test_named_empty_panel_save_and_clear_preserve_siblings(self):
        base = "/api/projects/ozgur/compliance-documents/"
        created = self.client.post(base, {
            "name": "A", "cover_page": {"number": "CP"},
            "panel": None, "panel_name": self.panel.name, "ata": None,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["panel_name"], self.panel.name)
        self.assertIsNone(created.data["ata"])
        empty_panel_id = created.data["panel"]
        url = base + created.data["id"] + "/"
        assigned = self.client.patch(url, {
            "version": 1, "panel": self.panel.pk, "ata": "27-00",
        }, format="json")
        self.assertEqual(assigned.status_code, 200, assigned.data)
        cleared = self.client.patch(url, {
            "version": 2, "panel": None, "panel_name": self.panel.name, "ata": None,
        }, format="json")
        self.assertEqual(cleared.status_code, 200, cleared.data)
        self.assertEqual(cleared.data["panel"], empty_panel_id)
        self.assertIsNone(cleared.data["ata"])
        self.assertEqual(Panel.objects.get(pk=empty_panel_id).ata, "")

    def test_export_preserves_empty_panel_name_and_ata(self):
        self.import_rows([{"name": "A", "cover_page_no": "CP", "panel": "New"}])
        response = self.client.get("/api/projects/ozgur/compliance-documents/export/")
        self.assertEqual(response.status_code, 200)
        frame = pd.read_excel(BytesIO(response.content)).fillna("")
        self.assertEqual(frame.iloc[0]["panel"], "New")
        self.assertEqual(frame.iloc[0]["ata"], "")

    def test_mixed_export_roundtrip_preserves_names_and_assignments(self):
        self.import_rows([
            {"name": "A", "cover_page_no": "CP", "panel": self.panel.name, "ata": 27},
            {"name": "B", "cover_page_no": "CP", "panel": "New", "ata": None},
        ])
        response = self.client.get("/api/projects/ozgur/compliance-documents/export/")
        preview = self.preview(response.content)
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["panel_changes"], [])
        self.assertEqual(preview.data["unchanged_count"], 2)

    def test_empty_panel_responsibles_can_be_filtered_by_id(self):
        ProjectRoleAssignment.objects.create(
            project=self.project, user=self.user, domain="organization", role="viewer",
        )
        first = Panel.objects.create(project=self.project, name="First", ata="")
        second = Panel.objects.create(project=self.project, name="Second", ata="")
        person = Person.objects.create(person_id="ATA-TEST", name="Engineer", email="engineer@example.test")
        for panel in (first, second):
            ResponsibleAssignment.objects.create(panel=panel, person=person, responsibility_role="AS")
        response = self.client.get(
            "/api/projects/ozgur/organization/responsible-assignments/", {"panel_id": first.pk},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["panel"], first.pk)

    def test_invalid_or_stale_named_panel_edits_do_not_create_catalog_entries(self):
        base = "/api/projects/ozgur/compliance-documents/"
        created = self.client.post(base, {
            "name": "A", "cover_page": {"number": "CP"},
        }, format="json")
        url = base + created.data["id"] + "/"
        response = self.client.patch(url, {
            "version": 2, "panel": None, "panel_name": "Stale", "ata": None,
        }, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        response = self.client.patch(url, {
            "version": 1, "panel": None, "panel_name": "Invalid", "ata": "27-00",
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Panel.objects.filter(project=self.project, ata="").exists())
