"""Project status catalog permissions, retention and import contracts."""
from datetime import date
from io import BytesIO
from unittest.mock import patch

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment
from .models import ComplianceDocument, CoverPage, WorkflowEvent


class StatusCatalogTests(TestCase):
    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.user = get_user_model().objects.create_user("status-manager")
        self.role = ProjectRoleAssignment.objects.create(
            project=self.project, user=self.user, domain="compliance", role="manager",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = "/api/projects/ozgur/compliance-documents/"

    def add(self, label):
        return self.client.post(self.base + "statuses/", {"label": label}, format="json")

    def document(self, status="unknown", **kwargs):
        cover = CoverPage.objects.create(project=self.project, number="CP")
        return ComplianceDocument.objects.create(
            project=self.project, cover_page=cover, name="Document", status=status, **kwargs,
        )

    def import_rows(self, rows, confirm=True, expected_status=201):
        output = BytesIO()
        pd.DataFrame([{"Cover Page Number": "CP", **row} for row in rows]).to_excel(output, index=False)
        def upload():
            return SimpleUploadedFile("statuses.xlsx", output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        preview = self.client.post(self.base + "imports/preview/", {"file": upload()}, format="multipart")
        self.assertEqual(preview.status_code, 200, preview.data)
        if not confirm:
            return preview
        result = self.client.post(self.base + "imports/confirm/", {
            "file": upload(), "confirmation_token": preview.data["confirmation_token"],
        }, format="multipart")
        self.assertEqual(result.status_code, expected_status, result.data)
        return result

    def test_catalog_normalization_permissions_and_reserved_values(self):
        response = self.add("  Custom   Review.  ")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["value"], "custom_review")
        self.assertEqual(self.add("CUSTOM REVIEW").status_code, 409)
        for invalid in ("", "...", "Delayed", "x" * 129, "bad\nstatus"):
            self.assertEqual(self.add(invalid).status_code, 400, invalid)
        options = self.client.get(self.base + "statuses/").data
        unknown = next(item for item in options if item["value"] == "unknown")
        self.assertFalse(unknown["can_delete"])
        self.assertEqual(self.client.delete(self.base + f'statuses/{unknown["id"]}/').status_code, 409)
        for role in ("editor", "viewer"):
            self.role.role = role
            self.role.save()
            self.assertEqual(self.client.get(self.base + "statuses/").status_code, 200)
            self.assertEqual(self.add("Not allowed").status_code, 403)
            self.assertEqual(self.client.delete(self.base + f'statuses/{response.data["id"]}/').status_code, 403)

    def test_current_and_archived_use_blocks_delete_but_history_does_not(self):
        option = self.add("Custom Review").data
        document = self.document("custom_review", is_archived=True)
        url = self.base + f'statuses/{option["id"]}/'
        self.assertEqual(self.client.delete(url).status_code, 409)
        WorkflowEvent.objects.create(document=document, sequence=1, status="custom_review", effective_date=date.today())
        document.status = "unknown"
        document.save()
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(document.workflow_events.get().status, "custom_review")

    def test_import_creates_options_only_on_confirmation_and_blank_updates_unknown(self):
        from .models import DocumentStatus
        rows = [{"Document Name": "Document", "Status": "Custom Review"}]
        preview = self.import_rows(rows, confirm=False)
        self.assertEqual(preview.data["status_changes"], [{"value": "custom_review", "label": "Custom Review"}])
        self.assertFalse(DocumentStatus.objects.filter(project=self.project, value="custom_review").exists())
        self.import_rows(rows)
        document = ComplianceDocument.objects.get()
        self.assertEqual(document.status, "custom_review")
        self.import_rows([{"Document Name": "Document"}])
        document.refresh_from_db()
        self.assertEqual(document.status, "unknown")
        self.assertEqual(list(document.workflow_events.order_by("sequence").values_list("status", flat=True)), ["custom_review", "unknown"])
        self.import_rows([{"Document Name": "Document"}])
        self.assertEqual(document.workflow_events.count(), 2)

    def test_options_are_project_scoped_and_transition_requires_catalog(self):
        option = self.add("Project Review")
        self.assertEqual(option.status_code, 201)
        other = Project.objects.exclude(pk=self.project.pk).first()
        ProjectRoleAssignment.objects.create(project=other, user=self.user, domain="compliance", role="manager")
        other_base = f"/api/projects/{other.slug}/compliance-documents/"
        self.assertEqual(self.client.delete(other_base + f'statuses/{option.data["id"]}/').status_code, 404)
        self.assertNotIn("project_review", [item["value"] for item in self.client.get(other_base + "statuses/").data])
        document = self.document()
        url = self.base + f"{document.pk}/transitions/"
        payload = {"version": 1, "status": "not_registered", "effective_date": "2026-09-29"}
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 400)
        payload["status"] = "project_review"
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 200)

    def test_missing_status_with_dates_and_dynamic_dashboard(self):
        self.import_rows([{"Document Name": "Document", "UBM Target Date": "2026-01-01"}])
        self.assertEqual(ComplianceDocument.objects.get().status, "unknown")
        self.import_rows([{"Document Name": "Other", "Status": "Custom Review"}])
        response = self.client.get(self.base + "dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("custom_review", str(response.data))

    def test_failed_rows_and_rollback_leave_no_options(self):
        from .models import DocumentStatus
        self.import_rows([{"Document Name": "", "Status": "Invalid only"}, {"Document Name": "Valid", "Status": "Valid only"}])
        self.assertFalse(DocumentStatus.objects.filter(value="invalid_only").exists())
        self.assertTrue(DocumentStatus.objects.filter(value="valid_only").exists())
        with patch("compliance.imports.transition_document", side_effect=RuntimeError("rollback")):
            self.import_rows([{"Document Name": "Rollback", "Status": "Rollback only"}], expected_status=500)
        self.assertFalse(DocumentStatus.objects.filter(value="rollback_only").exists())

    def test_multi_status_filter_and_labels_use_project_vocabulary(self):
        self.import_rows([
            {"Document Name": "First", "Status": "Engineering QA"},
            {"Document Name": "Second", "Status": "Review Complete"},
            {"Document Name": "Third"},
        ])
        response = self.client.get(self.base, {"status": ["engineering_qa", "review_complete"]})
        self.assertEqual(response.data["count"], 2)
        self.assertCountEqual([row["status_label"] for row in response.data["results"]], ["Engineering QA", "Review Complete"])
        fields = self.client.get(self.base + "fields/").data["fields"]
        choices = next(field["choices"] for field in fields if field["key"] == "status")
        self.assertCountEqual([item["value"] for item in choices], ["unknown", "engineering_qa", "review_complete"])

    def test_status_api_requires_csrf_and_authentication(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertIn(client.get(self.base + "statuses/").status_code, (401, 403))
        client.force_login(self.user)
        self.assertEqual(client.post(self.base + "statuses/", {"label": "CSRF"}).status_code, 403)

    def test_new_projects_receive_only_unknown(self):
        from .models import DocumentStatus
        project = Project.objects.create(slug="status-test", name="Status test")
        self.assertEqual(list(DocumentStatus.objects.filter(project=project).values_list("value", flat=True)), ["unknown"])

    def test_forward_seed_preserves_current_values_without_rewriting_history(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from .models import DocumentStatus
        document = self.document("existing_status")
        event = WorkflowEvent.objects.create(document=document, sequence=1, status="historical_only", effective_date=date.today())
        migration = import_module("compliance.migrations.0012_seed_project_statuses")
        migration.seed_statuses(apps, connection.schema_editor())
        self.assertEqual(set(DocumentStatus.objects.filter(project=self.project).values_list("value", flat=True)), {"unknown", "existing_status"})
        document.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(document.status, "existing_status")
        self.assertEqual(event.status, "historical_only")

    def test_blank_status_reimport_with_existing_milestones_appends_unknown(self):
        row = {"Document Name": "Document", "Status": "Custom Review",
               "UBM Target Date": "2026-01-01", "UBM Delivery Date": "2026-02-01"}
        self.import_rows([row])
        del row["Status"]
        self.import_rows([row])
        document = ComplianceDocument.objects.get()
        self.assertEqual(document.status, "unknown")
        self.assertEqual(document.ubm_delivery_date, date(2026, 2, 1))
        self.assertEqual(list(document.workflow_events.order_by("sequence").values_list("status", flat=True)), ["to_be_issued", "custom_review", "unknown"])

    def test_explicit_unknown_reimport_with_milestones_preserves_history(self):
        row = {"Document Name": "Document", "Status": "Custom Review",
               "UBM Target Date": "2026-01-01", "UBM Delivery Date": "2026-02-01"}
        self.import_rows([row])
        row["Status"] = "Unknown"
        self.import_rows([row])
        document = ComplianceDocument.objects.get()
        self.assertEqual(document.status, "unknown")
        self.assertEqual(document.workflow_events.count(), 3)
