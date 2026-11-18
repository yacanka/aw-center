"""End-to-end catalog contracts with disposable documents and a stubbed JIRA issue."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from docx import Document
from rest_framework.test import APIClient

from jobs.tests.base import JobTestCase
from orgs.models import Project, ProjectRoleAssignment
from .template_models import JiraDocumentTemplate


ROOT = "/api/integrations/jira/"
CATALOG = ROOT + "document-templates/"
ISSUE = {
    "issue": "EX-10", "project_id": "12", "project_name": "Example",
    "issue_type_id": "7", "issue_type_name": "Sub-task",
    "fields": [{"id": "summary", "name": "Summary", "value": "Sample data", "supported": True}],
}


def upload(*names):
    document = Document()
    for name in names:
        document.add_paragraph("{{" + name + "}}")
    data = BytesIO()
    document.save(data)
    return SimpleUploadedFile("form.docx", data.getvalue(), "application/octet-stream")


@override_settings(JIRA_URL="https://jira.example.test")
class DocumentTemplateCatalogTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="integrations", codename="manage_jira_document_templates"
        ))

    def publish(self):
        with patch("integrations.jira.template_catalog.read_template_issue", return_value=ISSUE):
            response = self.client.post(CATALOG, {
                "name": "Report", "issue": "EX-10", "mapping": '{"Başlık":"summary"}',
                "file": upload("Başlık", "Notes", "Başlık"),
            }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        return CATALOG + str(response.data["id"]) + "/"

    def test_permission_scope_and_private_source(self):
        path = self.publish()
        template = JiraDocumentTemplate.objects.get()
        source = self.client.get(path + "source/")
        self.assertEqual(source.status_code, 200)
        self.assertTrue(b"".join(source.streaming_content).startswith(b"PK"))
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(CATALOG).status_code, 200)
        payload = self.client.get(path).data
        self.assertNotIn("source_file", payload)
        self.assertNotIn("Sample data", str(payload))
        self.assertEqual(self.client.get(path + "source/").status_code, 403)
        ProjectRoleAssignment.objects.create(user=self.other_user, project=Project.objects.first(),
                                            domain="jira", role="publisher")
        self.assertEqual(self.client.patch(path, {"version": 1, "archived": True}, format="json").status_code, 403)
        self.client.force_authenticate(self.user)
        Path(template.source_file.path).write_bytes(b"changed")
        self.assertEqual(self.client.get(path + "source/").status_code, 500)
        template.created_by.delete()
        template.refresh_from_db()
        self.assertIsNone(template.created_by_id)

    def test_replace_reconciles_fields_and_rejects_stale_archive(self):
        path = self.publish()
        with patch("integrations.jira.template_catalog.read_template_issue", return_value=ISSUE):
            with self.captureOnCommitCallbacks(execute=True):
                updated = self.client.patch(path, {"version": 1, "issue": "EX-10",
                                            "file": upload("Başlık", "Yeni")}, format="multipart")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["mapping"], {"Başlık": "summary"})
        self.assertEqual(updated.data["placeholders"], [{"name": "Başlık", "count": 1}, {"name": "Yeni", "count": 1}])
        stale = self.client.patch(path, {"version": 1, "archived": True}, format="json")
        self.assertEqual(stale.status_code, 409)
        archived = self.client.patch(path, {"version": 2, "archived": True}, format="json")
        self.assertEqual(archived.status_code, 200)
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get(CATALOG).data, {"templates": []})

    @patch("integrations.jira.template_views.read_template_issue", return_value=ISSUE)
    def test_match_uses_native_ids_and_returns_multiple_choices(self, read_issue):
        self.publish()
        self.publish()
        self.client.force_authenticate(self.other_user)
        def matches():
            response = self.client.post(ROOT + "document-generation/resolve/", {"issue": "EX-10"}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            return response.data["templates"]
        with self.settings(JIRA_URL="https://JIRA.EXAMPLE.TEST:443/"):
            self.assertEqual(len(matches()), 2)
        with self.settings(JIRA_URL="https://jira.example.test/other"):
            self.assertEqual(matches(), [])
        read_issue.return_value = {**ISSUE, "issue_type_id": "8"}
        self.assertEqual(matches(), [])
        read_issue.return_value = {**ISSUE, "project_id": "other"}
        self.assertEqual(matches(), [])

    def test_unsupported_mapping_and_untrusted_identifiers_are_rejected(self):
        invalid = {"name": "Example", "file": upload("Name"), "issue": "EX-10", "mapping": '{"Name":"absent"}'}
        with patch("integrations.jira.template_catalog.read_template_issue", return_value=ISSUE):
            self.assertEqual(self.client.post(CATALOG, invalid, format="multipart").status_code, 400)
        self.assertEqual(self.client.post(CATALOG, {"project_id": "forged"}, format="json").status_code, 400)
        self.assertFalse(JiraDocumentTemplate.objects.exists())

    def test_non_object_requests_return_validation_error(self):
        for path in (CATALOG, ROOT + "document-generation/resolve/", ROOT + "document-generation/jobs/"):
            response = self.client.post(path, [{}], format="json")
            self.assertEqual(response.status_code, 400, path)
            self.assertEqual(response.data["code"], "VALIDATION_ERROR")

    def test_authentication_and_csrf_before_jira_or_file_access(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertIn(client.get(CATALOG).status_code, (401, 403))
        client.force_login(get_user_model().objects.get(pk=self.user.pk))
        self.assertEqual(client.post(CATALOG + "inspect/", {"file": upload("A")}).status_code, 403)
