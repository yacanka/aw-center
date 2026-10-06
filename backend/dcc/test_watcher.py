"""Regression coverage for restored Watcher workflows."""
from types import SimpleNamespace as NS
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment
from .models import DccRecord


@override_settings(JIRA_URL="https://jira.example.test", JIRA_ENABLED=True)
class WatcherTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("watcher-owner")
        self.project = Project.objects.get(slug="hys")
        ProjectRoleAssignment.objects.create(user=self.user, project=self.project,
            domain="dcc", role="operator")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def issue(self, *, subtask=False):
        return NS(key="CHN-42", fields=NS(summary="Change document",
            components=[NS(name="HYS")], issuetype=NS(subtask=subtask),
            status=NS(name="In Progress", statusCategory=NS(key="indeterminate")),
            subtasks=[NS(key="CHN-43", fields=NS(summary="Safety", status=NS(
                name="In Review", statusCategory=NS(key="indeterminate"))))],
            customfield_45000="ECD-1", customfield_45001="A", customfield_45002="DCC-1"))

    def record(self):
        record = DccRecord.objects.create(owner=self.user, issue="CHN-42", title="Change")
        record.projects.add(self.project)
        return record

    @patch("dcc.watcher_service.jira_connector_for")
    def test_import_url_resolves_title_projects_and_rejects_duplicate(self, factory):
        factory.return_value.get_issue.return_value = self.issue()
        payload = {"issue": "https://jira.example.test/browse/CHN-42"}
        first = self.client.post("/api/dcc/records/import/", payload, format="json")
        second = self.client.post("/api/dcc/records/import/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["title"], "Change document")
        self.assertEqual(first.data["project_slugs"], ["hys"])
        self.assertEqual(second.status_code, 409)
        self.assertEqual(DccRecord.objects.count(), 1)
        factory.return_value.set_issue.assert_called_with("CHN-42")

    @patch("dcc.watcher_service.jira_connector_for")
    def test_import_requires_all_project_roles_and_parent_task(self, factory):
        factory.return_value.get_issue.return_value = self.issue(subtask=True)
        response = self.client.post("/api/dcc/records/import/", {"issue": "CHN-42"})
        self.assertEqual(response.status_code, 400)
        factory.return_value.get_issue.return_value = self.issue()
        ProjectRoleAssignment.objects.all().delete()
        response = self.client.post("/api/dcc/records/import/", {"issue": "CHN-42"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DccRecord.objects.exists())

    @patch("dcc.watcher_service.jira_connector_for")
    def test_live_status_treats_in_review_as_unfinished_and_bounds_payload(self, factory):
        record = self.record()
        factory.return_value.get_issue.return_value = self.issue()
        response = self.client.post(f"/api/dcc/records/{record.id}/status/", {})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["completed"])
        self.assertEqual(response.data["subtasks"][0]["status"], "In Review")
        self.assertEqual(response.data["subtasks"][0]["jira_issue_url"],
                         "https://jira.example.test/browse/CHN-43")
        self.assertNotIn("fields", response.data)
        self.assertNotIn("raw", response.data)

    @patch("dcc.watcher_service.jira_connector_for")
    def test_outsider_cannot_trigger_jira_lookup(self, factory):
        record = self.record()
        self.client.force_authenticate(get_user_model().objects.create_user("outsider"))
        response = self.client.post(f"/api/dcc/records/{record.id}/status/", {})
        self.assertEqual(response.status_code, 404)
        factory.assert_not_called()

    def test_filters_apply_before_pagination(self):
        record = self.record()
        record.active = False
        record.save()
        self.assertEqual(self.client.get("/api/dcc/records/?active=true").data["count"], 0)
        self.assertEqual(self.client.get("/api/dcc/records/?issue=CHN&active=false").data["count"], 1)
        self.assertEqual(self.client.get("/api/dcc/records/?title=missing").data["count"], 0)

    @patch("dcc.watcher_assessment.request_assessment", return_value="1: Safety: Major - Review")
    @patch("dcc.watcher_assessment.parse_ecr_pdf")
    def test_pdf_assessment_uses_canonical_parser_and_adapter(self, parse, assess):
        parse.return_value = {"title": "Change", "justification": "Reason"}
        response = self.client.post("/api/dcc/assessments/", {
            "project_slugs": ["hys"],
            "file": SimpleUploadedFile("ecr.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        }, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("Safety", response.data["assessment"])
        self.assertIn("Reason", assess.call_args.args[0])
        self.assertIn("Human Factors", assess.call_args.args[0])

    @patch("dcc.watcher_service.jira_connector_for")
    def test_invalid_and_foreign_urls_never_reach_jira(self, factory):
        for reference in ("https://untrusted.example/browse/CHN-42", "CHN-42 garbage",
                          "https://jira.example.test/browse/CHN-42/extra", "CHN-0",
                          "https://[bad/browse/CHN-42"):
            with self.subTest(reference=reference):
                response = self.client.post("/api/dcc/records/import/", {"issue": reference})
                self.assertEqual(response.status_code, 400)
        factory.assert_not_called()

    @patch("dcc.watcher_service.jira_connector_for")
    def test_legacy_credentials_rejected(self, factory):
        record = self.record()
        for url in ("/api/dcc/records/import/", f"/api/dcc/records/{record.id}/status/"):
            response = self.client.post(url, {"issue": "CHN-42", "JSESSIONID": "unusable"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["code"], "JIRA_SESSION_CANONICAL_REQUIRED")
        factory.assert_not_called()

    @patch("dcc.watcher_service.jira_connector_for")
    def test_done_category_and_empty_subtasks_use_correct_completion(self, factory):
        record = self.record()
        issue = self.issue()
        issue.fields.subtasks[0].fields.status = NS(name="Accepted", statusCategory=NS(key="done"))
        factory.return_value.get_issue.return_value = issue
        url = f"/api/dcc/records/{record.id}/status/"
        self.assertTrue(self.client.post(url, {}).data["completed"])
        issue.fields.subtasks = []
        self.assertFalse(self.client.post(url, {}).data["completed"])
        issue.fields.status = NS(name="Closed")
        self.assertTrue(self.client.post(url, {}).data["completed"])

    @patch("dcc.watcher_service.jira_connector_for")
    def test_project_drift_and_subtask_limit_are_rejected(self, factory):
        record = self.record()
        issue = self.issue()
        factory.return_value.get_issue.return_value = issue
        record.projects.add(Project.objects.get(slug="gokbey"))
        ProjectRoleAssignment.objects.create(user=self.user, project=Project.objects.get(slug="gokbey"), domain="dcc", role="operator")
        url = f"/api/dcc/records/{record.id}/status/"
        self.assertEqual(self.client.post(url, {}).status_code, 409)
        issue.fields.subtasks *= 201
        self.assertEqual(self.client.post(url, {}).data["code"], "DCC_TOO_MANY_SUBTASKS")

    @patch("dcc.watcher_service.jira_connector_for")
    def test_jira_failure_does_not_expose_upstream_text(self, factory):
        from jira import JIRAError
        factory.return_value.get_issue.side_effect = JIRAError(status_code=500, text="private upstream details")
        response = self.client.post("/api/dcc/records/import/", {"issue": "CHN-42"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private upstream", str(response.data))
        self.assertIn("request_id", response.data)

    @patch("dcc.watcher_assessment.parse_ecr_pdf")
    def test_assessment_access_and_upload_validation_happen_before_parsing(self, parse):
        response = self.client.post("/api/dcc/assessments/", {
            "project_slugs": ["hys"],
            "file": SimpleUploadedFile("ecr.pdf", b"not a pdf", content_type="application/pdf"),
        }, format="multipart")
        self.assertEqual(response.status_code, 400)
        ProjectRoleAssignment.objects.all().delete()
        response = self.client.post("/api/dcc/assessments/", {"project_slugs": ["hys"]}, format="multipart")
        self.assertEqual(response.status_code, 403)
        parse.assert_not_called()

    @patch("dcc.watcher_assessment.request_assessment")
    @patch("dcc.watcher_assessment.parse_ecr_pdf")
    def test_assessment_reports_parser_and_service_errors(self, parse, assess):
        from automations.ecr_parser import EcrPdfParseError
        from integrations.assessment import AssessmentServiceError
        for failure in ("parse", "service"):
            parse.side_effect = EcrPdfParseError("internal") if failure == "parse" else None
            parse.return_value = {"title": "Change"}
            assess.side_effect = AssessmentServiceError("Service unavailable.", "ASSESSMENT_UNAVAILABLE", 503)
            response = self.client.post("/api/dcc/assessments/", {
                "project_slugs": ["hys"],
                "file": SimpleUploadedFile("ecr.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
            }, format="multipart")
            self.assertEqual(response.status_code, 400 if failure == "parse" else 503)
            self.assertNotIn("internal", str(response.data))

    def test_watcher_unsafe_endpoints_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        for url in ("/api/dcc/records/import/", "/api/dcc/assessments/"):
            self.assertEqual(client.post(url, {}).status_code, 403)

    @patch("dcc.watcher_service.jira_connector_for")
    def test_import_uses_canonical_key_when_jira_redirects(self, factory):
        issue = self.issue()
        issue.key = "NEW_2-42"
        factory.return_value.get_issue.return_value = issue
        response = self.client.post("/api/dcc/records/import/", {"issue": "OLD-42"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["issue"], "NEW_2-42")

    def test_publication_tracking_does_not_overwrite_existing_record(self):
        from .record_services import track_published_issue
        existing = self.record()
        tracked = track_published_issue(self.user, existing.issue, "New title", [self.project])
        self.assertEqual(tracked.pk, existing.pk)
        self.assertEqual(tracked.title, "Change")
        self.assertEqual(DccRecord.objects.count(), 1)
