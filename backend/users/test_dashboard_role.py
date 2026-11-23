"""Dashboard-only sessions keep project access and scope all other surfaces."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from compliance.models import ComplianceDocument, CoverPage, DoorsImportMapping
from jobs.models import Job, JobStatus
from orgs.models import Project, ProjectRoleAssignment


class DashboardRoleTests(TestCase):
    def setUp(self):
        self.group = Group.objects.filter(name="Dashboard User").first()
        self.user = get_user_model().objects.create_user(username="d12345", password="StrongPass!123")
        self.project = Project.objects.get(slug="ozgur")
        self.other_project = Project.objects.get(slug="hurjet")
        self.client = APIClient(enforce_csrf_checks=True)

    def login(self, *, dashboard_only=True):
        if dashboard_only:
            self.assertIsNotNone(self.group)
            self.user.groups.add(self.group)
        token = self.client.get("/api/session/").cookies["csrftoken"].value
        return self.client.post(
            "/api/session/", {"username": self.user.username, "password": "StrongPass!123"},
            format="json", HTTP_X_CSRFTOKEN=token,
        )

    def grant(self, project, domain, role):
        ProjectRoleAssignment.objects.create(user=self.user, project=project, domain=domain, role=role)

    def assert_dashboard_restricted(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "DASHBOARD_ACCESS_REQUIRED")
        self.assertIn("request_id", response.json())

    def test_session_reports_the_seeded_role_and_preserves_logout_csrf(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.data["user"]["dashboard_only"], True)
        self.assertIs(self.client.get("/api/session/").data["user"]["dashboard_only"], True)
        self.assertEqual(self.client.delete("/api/session/").status_code, 403)
        response = self.client.delete(
            "/api/session/", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 204)

    def test_regular_session_keeps_full_access(self):
        response = self.login(dashboard_only=False)
        self.assertIs(response.data["user"]["dashboard_only"], False)
        self.assertEqual(self.client.get("/api/jobs/").status_code, 200)
        self.user.groups.add(self.group)
        self.assert_dashboard_restricted(self.client.get("/api/jobs/"))
        self.user.groups.remove(self.group)
        self.assertEqual(self.client.get("/api/jobs/").status_code, 200)

    def test_catalog_and_documents_remain_compliance_authorized(self):
        self.grant(self.project, "compliance", "viewer")
        self.grant(self.project, "jira", "operator")
        self.grant(self.other_project, "organization", "manager")
        self.login()

        response = self.client.get("/api/projects/")
        self.assertEqual(response.data, [{
            "slug": "ozgur", "name": "Özgür", "capabilities": ["compliance"],
            "roles": {"compliance": "viewer", "organization": None, "jira": None},
        }])
        self.assertEqual(self.client.get("/api/projects/?capability=jira").data, [])
        for suffix in ("", "dashboard/"):
            self.assertEqual(self.client.get(f"/api/projects/ozgur/compliance-documents/{suffix}").status_code, 200)
            denied = self.client.get(f"/api/projects/hurjet/compliance-documents/{suffix}")
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.data["code"], "PROJECT_ROLE_REQUIRED")

    def test_extra_privileges_cannot_open_unrelated_endpoints(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        self.login()

        for url in (
            "/api/attention/", "/api/integrations/", "/api/users/", "/api/users/groups/",
            "/api/projects/ozgur/organization/panels/", "/api/jobs/", "/api/jobs/system/",
            "/api/management-reports/reports/", "/api/tools/word/jobs/translate/",
        ):
            with self.subTest(url=url):
                self.assert_dashboard_restricted(self.client.get(url))
        self.assertEqual(self.client.get("/admin/").status_code, 403)
        self.assertEqual(self.client.get("/api/users/preferences/").status_code, 200)

    def test_linked_tools_and_job_access_remain_owner_and_feature_scoped(self):
        self.login()
        own_analysis = Job.objects.create(owner=self.user, kind="word.analyze", title="Analysis")
        other_job = Job.objects.create(owner=self.user, kind="word.translate", title="Translation")
        handoff = Job.objects.create(
            owner=self.user, kind="word.analyze", title="Workflow analysis", source_job=other_job,
        )
        other_user = get_user_model().objects.create_user(username="o12345")
        other_analysis = Job.objects.create(owner=other_user, kind="word.analyze", title="Analysis")

        self.assertEqual(self.client.get("/api/tools/word/analysis-checks/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/jobs/{own_analysis.pk}/").status_code, 200)
        for job in (other_job, handoff, other_analysis):
            self.assertEqual(self.client.get(f"/api/jobs/{job.pk}/").status_code, 404)
            self.assertEqual(self.client.get(f"/api/jobs/{job.pk}/download/").status_code, 404)

        token = self.client.cookies["csrftoken"].value
        cancellation_url = f"/api/jobs/{own_analysis.pk}/cancel/"
        self.assertEqual(self.client.post(cancellation_url).status_code, 403)
        self.assertEqual(self.client.post(cancellation_url, HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_project_job_access_requires_a_current_editor_role(self):
        self.grant(self.project, "compliance", "editor")
        self.login()
        job = Job.objects.create(
            owner=self.user, kind="compliance.describe_numbering_format", title="Number format",
            parameters={"project_slug": self.project.slug},
        )
        path = f"/api/jobs/{job.pk}/"
        self.assertEqual(self.client.get(path).status_code, 200)

        self.project.enabled = False
        self.project.save(update_fields=["enabled"])
        self.assertEqual(self.client.get(path).status_code, 404)

    @patch("integrations.docproof_views.search_document_issue", return_value=("B", None))
    def test_docproof_search_only_looks_up_visible_register_documents(self, upstream):
        self.grant(self.project, "compliance", "viewer")
        for project, number in ((self.project, "VISIBLE/01"), (self.other_project, "PRIVATE")):
            cover_page = CoverPage.objects.create(project=project, number="CP-1")
            ComplianceDocument.objects.create(project=project, cover_page=cover_page, name=number, number=number)
        self.login()

        url = "/api/integrations/docproof/search/"
        for number in ("PRIVATE", "VISIBLE-EXTRA", "UNRELATED"):
            self.assertEqual(self.client.get(url, {"document_no": number}).status_code, 403)
        upstream.assert_not_called()
        response = self.client.get(url, {"document_no": "VISIBLE"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, "B")
        upstream.assert_called_once_with("VISIBLE")

    @patch("integrations.doors.api_views.worker_unavailable_response", return_value=None)
    def test_doors_export_uses_only_mapped_project_sources(self, _worker_health):
        for project in (self.project, self.other_project):
            self.grant(project, "compliance", "editor")
        module = "/Synthetic/Compliance"
        DoorsImportMapping.objects.create(project=self.project, module_path=module, successful_at=timezone.now())
        self.login()
        url = "/api/integrations/doors/module-export-jobs/"
        headers = {
            "HTTP_X_CSRFTOKEN": self.client.cookies["csrftoken"].value,
            "HTTP_IDEMPOTENCY_KEY": "dashboard-doors-fixture",
        }
        response = self.client.post(url, {"module_path": "/Unmapped/Module"}, format="json", **headers)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Job.objects.exists())

        with TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=Path(directory)):
            response = self.client.post(url, {"module_path": module}, format="json", **headers)
            self.assertEqual(response.status_code, 201, response.data)
            job = Job.objects.get(pk=response.data["id"])
            encoded = json.dumps({
                "type": "doors_module_export", "schema_version": 1, "module_path": module,
                "columns": ["Title"], "count": 1, "results": [{"attributes": {"Title": "Document"}}],
            }).encode()
            job.status = JobStatus.SUCCEEDED
            job.output_name = "doors-result.json"
            job.output_sha256 = hashlib.sha256(encoded).hexdigest()
            job.output_file.save(job.output_name, ContentFile(encoded), save=True)

            self.assertEqual(self.client.get(f"/api/jobs/{job.pk}/").status_code, 200)
            self.assertEqual(self.client.get(f"/api/jobs/{job.pk}/download/").status_code, 404)
            for project, expected in ((self.project, 200), (self.other_project, 404)):
                response = self.client.get(
                    f"/api/projects/{project.slug}/compliance-documents/imports/doors/sources/{job.pk}/",
                )
                self.assertEqual(response.status_code, expected, response.data)

    def test_seeded_group_can_be_assigned_but_has_a_stable_identity(self):
        self.assertIsNotNone(self.group)
        admin = get_user_model().objects.create_superuser(username="a12345")
        self.client.force_login(admin)
        token = self.client.get("/api/session/").cookies["csrftoken"].value
        url = f"/api/users/groups/{self.group.pk}/"

        payload = self.client.get(url).data
        self.assertEqual(payload["name"], "Dashboard User")
        self.assertIs(payload["is_builtin"], True)
        assignment = self.client.patch(
            f"/api/users/{self.user.pk}/", {"groups": [self.group.pk]},
            format="json", HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(assignment.status_code, 200, assignment.data)
        self.assertEqual(assignment.data["groups"], [self.group.pk])
        self.assertEqual(self.client.patch(
            url, {"name": "Other Role"}, format="json", HTTP_X_CSRFTOKEN=token,
        ).status_code, 403)
        self.assertEqual(self.client.delete(url, HTTP_X_CSRFTOKEN=token).status_code, 403)
        self.assertEqual(self.client.get(f"/admin/auth/group/{self.group.pk}/delete/").status_code, 403)
        self.client.post(
            "/admin/auth/group/",
            {"action": "delete_selected", "_selected_action": self.group.pk, "post": "yes"},
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertTrue(Group.objects.filter(pk=self.group.pk, name="Dashboard User").exists())
        self.client.logout()
        self.assertIs(self.login(dashboard_only=False).data["user"]["dashboard_only"], True)

    def test_dashboard_user_can_change_theme_only_and_still_needs_csrf(self):
        self.login()
        url = "/api/users/preferences/"
        token = self.client.cookies["csrftoken"].value
        self.assertEqual(self.client.patch(url, {"theme": "dark"}, format="json").status_code, 403)
        response = self.client.patch(url, {"theme": "dark"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["theme"], "dark")
        response = self.client.patch(url, {"theme": "light", "email_notifications": False},
                                     format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(url).data["theme"], "dark")
