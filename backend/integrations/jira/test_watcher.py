"""Regression coverage for restored Watcher workflows."""
from types import SimpleNamespace as NS
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment
from .workflow_models import JiraTrackedIssue


@override_settings(JIRA_URL="https://jira.example.test", JIRA_ENABLED=True)
class WatcherTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("watcher-owner")
        self.project = Project.objects.get(slug="hys")
        ProjectRoleAssignment.objects.create(user=self.user, project=self.project,
            domain="jira", role="operator")
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
        record = JiraTrackedIssue.objects.create(owner=self.user, issue="CHN-42", title="Change")
        record.projects.add(self.project)
        return record

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_import_url_resolves_title_projects_and_rejects_duplicate(self, factory):
        factory.return_value.get_issue.return_value = self.issue()
        payload = {"issue": "https://jira.example.test/browse/CHN-42"}
        first = self.client.post("/api/integrations/jira/records/import/", payload, format="json")
        second = self.client.post("/api/integrations/jira/records/import/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["title"], "Change document")
        self.assertEqual(first.data["project_slugs"], ["hys"])
        self.assertEqual(first.data["components"], ["HYS"])
        self.assertEqual(second.status_code, 409)
        self.assertEqual(JiraTrackedIssue.objects.count(), 1)
        factory.return_value.set_issue.assert_called_with("CHN-42")

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_import_requires_all_project_roles_and_parent_task(self, factory):
        factory.return_value.get_issue.return_value = self.issue(subtask=True)
        response = self.client.post("/api/integrations/jira/records/import/", {"issue": "CHN-42"})
        self.assertEqual(response.status_code, 400)
        factory.return_value.get_issue.return_value = self.issue()
        ProjectRoleAssignment.objects.all().delete()
        response = self.client.post("/api/integrations/jira/records/import/", {"issue": "CHN-42"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(JiraTrackedIssue.objects.exists())

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_live_status_treats_in_review_as_unfinished_and_bounds_payload(self, factory):
        record = self.record()
        factory.return_value.get_issue.return_value = self.issue()
        response = self.client.post(f"/api/integrations/jira/records/{record.id}/status/", {})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["completed"])
        self.assertEqual(response.data["subtasks"][0]["status"], "In Review")
        self.assertEqual(response.data["subtasks"][0]["jira_issue_url"],
                         "https://jira.example.test/browse/CHN-43")
        self.assertNotIn("fields", response.data)
        self.assertNotIn("raw", response.data)

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_outsider_cannot_trigger_jira_lookup(self, factory):
        record = self.record()
        self.client.force_authenticate(get_user_model().objects.create_user("outsider"))
        response = self.client.post(f"/api/integrations/jira/records/{record.id}/status/", {})
        self.assertEqual(response.status_code, 404)
        factory.assert_not_called()

    def test_filters_apply_before_pagination(self):
        record = self.record()
        record.active = False
        record.save()
        self.assertEqual(self.client.get("/api/integrations/jira/records/?active=true").data["count"], 1)
        self.assertEqual(self.client.get("/api/integrations/jira/records/?issue=CHN&active=false").data["count"], 1)
        self.assertEqual(self.client.get("/api/integrations/jira/records/?title=missing").data["count"], 0)

    @patch("integrations.jira.watcher_assessment.request_assessment", return_value="1: Safety: Major - Review")
    @patch("integrations.jira.watcher_assessment.parse_ecr_pdf")
    def test_pdf_assessment_uses_canonical_parser_and_adapter(self, parse, assess):
        parse.return_value = {"title": "Change", "justification": "Reason"}
        response = self.client.post("/api/integrations/jira/assessments/", {
            "project_slugs": ["hys"],
            "file": SimpleUploadedFile("ecr.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        }, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("Safety", response.data["assessment"])
        self.assertIn("Reason", assess.call_args.args[0])
        self.assertIn("Human Factors", assess.call_args.args[0])

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_invalid_and_foreign_urls_never_reach_jira(self, factory):
        for reference in ("https://untrusted.example/browse/CHN-42", "CHN-42 garbage",
                          "https://jira.example.test/browse/CHN-42/extra", "CHN-0",
                          "https://[bad/browse/CHN-42"):
            with self.subTest(reference=reference):
                response = self.client.post("/api/integrations/jira/records/import/", {"issue": reference})
                self.assertEqual(response.status_code, 400)
        factory.assert_not_called()

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_legacy_credentials_rejected(self, factory):
        record = self.record()
        for url in ("/api/integrations/jira/records/import/", f"/api/integrations/jira/records/{record.id}/status/"):
            response = self.client.post(url, {"issue": "CHN-42", "JSESSIONID": "unusable"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["code"], "JIRA_SESSION_CANONICAL_REQUIRED")
        factory.assert_not_called()

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_done_category_and_empty_subtasks_use_correct_completion(self, factory):
        record = self.record()
        issue = self.issue()
        issue.fields.subtasks[0].fields.status = NS(name="Accepted", statusCategory=NS(key="done"))
        factory.return_value.get_issue.return_value = issue
        url = f"/api/integrations/jira/records/{record.id}/status/"
        self.assertTrue(self.client.post(url, {}).data["completed"])
        issue.fields.subtasks = []
        self.assertFalse(self.client.post(url, {}).data["completed"])
        issue.fields.status = NS(name="Closed")
        self.assertTrue(self.client.post(url, {}).data["completed"])

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_project_drift_and_subtask_limit_are_rejected(self, factory):
        record = self.record()
        issue = self.issue()
        factory.return_value.get_issue.return_value = issue
        record.projects.add(Project.objects.get(slug="gokbey"))
        ProjectRoleAssignment.objects.create(user=self.user, project=Project.objects.get(slug="gokbey"), domain="jira", role="operator")
        url = f"/api/integrations/jira/records/{record.id}/status/"
        self.assertEqual(self.client.post(url, {}).status_code, 409)
        issue.fields.subtasks *= 201
        self.assertEqual(self.client.post(url, {}).data["code"], "DCC_TOO_MANY_SUBTASKS")

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_jira_failure_does_not_expose_upstream_text(self, factory):
        from jira import JIRAError
        factory.return_value.get_issue.side_effect = JIRAError(status_code=500, text="private upstream details")
        response = self.client.post("/api/integrations/jira/records/import/", {"issue": "CHN-42"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private upstream", str(response.data))
        self.assertIn("request_id", response.data)

    @patch("integrations.jira.watcher_assessment.parse_ecr_pdf")
    def test_assessment_access_and_upload_validation_happen_before_parsing(self, parse):
        response = self.client.post("/api/integrations/jira/assessments/", {
            "project_slugs": ["hys"],
            "file": SimpleUploadedFile("ecr.pdf", b"not a pdf", content_type="application/pdf"),
        }, format="multipart")
        self.assertEqual(response.status_code, 400)
        ProjectRoleAssignment.objects.all().delete()
        response = self.client.post("/api/integrations/jira/assessments/", {"project_slugs": ["hys"]}, format="multipart")
        self.assertEqual(response.status_code, 403)
        parse.assert_not_called()

    @patch("integrations.jira.watcher_assessment.request_assessment")
    @patch("integrations.jira.watcher_assessment.parse_ecr_pdf")
    def test_assessment_reports_parser_and_service_errors(self, parse, assess):
        from automations.ecr_parser import EcrPdfParseError
        from integrations.assessment import AssessmentServiceError
        for failure in ("parse", "service"):
            parse.side_effect = EcrPdfParseError("internal") if failure == "parse" else None
            parse.return_value = {"title": "Change"}
            assess.side_effect = AssessmentServiceError("Service unavailable.", "ASSESSMENT_UNAVAILABLE", 503)
            response = self.client.post("/api/integrations/jira/assessments/", {
                "project_slugs": ["hys"],
                "file": SimpleUploadedFile("ecr.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
            }, format="multipart")
            self.assertEqual(response.status_code, 400 if failure == "parse" else 503)
            self.assertNotIn("internal", str(response.data))

    def test_watcher_unsafe_endpoints_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        for url in ("/api/integrations/jira/records/import/", "/api/integrations/jira/assessments/"):
            self.assertEqual(client.post(url, {}).status_code, 403)

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_import_uses_canonical_key_when_jira_redirects(self, factory):
        issue = self.issue()
        issue.key = "NEW_2-42"
        factory.return_value.get_issue.return_value = issue
        response = self.client.post("/api/integrations/jira/records/import/", {"issue": "OLD-42"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["issue"], "NEW_2-42")

    def test_publication_tracking_does_not_overwrite_existing_record(self):
        from .record_services import track_published_issue
        existing = self.record()
        tracked = track_published_issue(self.user, existing.issue, "New title", [self.project])
        self.assertEqual(tracked.pk, existing.pk)
        self.assertEqual(tracked.title, "Change")
        self.assertEqual(JiraTrackedIssue.objects.count(), 1)

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_sync_refreshes_trusted_title_and_separates_parent_completion(self, factory):
        record = self.record()
        issue = self.issue()
        issue.fields.subtasks[0].fields.status = NS(name="Accepted", statusCategory=NS(key="done"))
        factory.return_value.get_issue.return_value = issue
        response = self.client.post(f"/api/integrations/jira/records/{record.id}/status/", {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["completed"])
        self.assertFalse(response.data["issue_completed"])
        record.refresh_from_db()
        self.assertEqual(record.title, "Change document")
        self.assertEqual(response.data["record_version"], record.version)
        self.assertEqual(record.version, 2)
        self.client.post(f"/api/integrations/jira/records/{record.id}/status/", {})
        record.refresh_from_db()
        self.assertEqual(record.version, 2)

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_detail_fields_use_issue_names_and_safe_display_values(self, factory):
        record = self.record()
        issue = self.issue()
        issue.names = {"customfield_12345": "Applicability", "customfield_54321": "Unknown"}
        issue.fields.customfield_12345 = [NS(value="Variant A"), NS(value="Variant B")]
        issue.fields.customfield_54321 = NS(internal="do not expose object representation")
        issue.fields.attachment = [{"content": "do not expose URL"}]
        issue.fields.assignee = NS(displayName="Example user", emailAddress="excluded@example.test")
        factory.return_value.get_issue.return_value = issue
        response = self.client.post(f"/api/integrations/jira/records/{record.id}/status/", {})
        self.assertEqual(response.status_code, 200)
        values = {item["id"]: item for item in response.data["detail_fields"]}
        self.assertEqual(values["customfield_12345"], {
            "id": "customfield_12345", "label": "Applicability", "value": "Variant A, Variant B"})
        self.assertEqual(values["assignee"]["value"], "Example user")
        self.assertEqual(values["customfield_54321"]["value"], "")
        self.assertNotIn("attachment", values)
        self.assertNotIn("excluded@example.test", str(response.data))
        self.assertEqual(response.data["project_slugs"], ["hys"])

    def test_manual_title_and_active_changes_are_rejected(self):
        record = self.record()
        for key, value in (("title", "Manual title"), ("active", False)):
            response = self.client.patch(f"/api/integrations/jira/records/{record.id}/", {
                key: value, "version": record.version}, format="json")
            self.assertEqual(response.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(record.title, "Change")
        self.assertEqual(record.version, 1)
        self.assertNotIn("active", self.client.get("/api/integrations/jira/records/").data["results"][0])

    def test_preferences_are_user_bound_and_preserve_unrelated_settings(self):
        preferences = self.user.preferences
        preferences.extra_settings = {"other": {"keep": True}}
        preferences.save()
        url = "/api/integrations/jira/watcher/preferences/"
        self.assertEqual(self.client.get(url).data, {"outstanding_only": False, "detail_fields": {}, "component_fields": {}})
        response = self.client.patch(url, {"project_slug": "hys", "detail_field_ids": [
            "customfield_45000", "priority"], "outstanding_only": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {"outstanding_only": True,
            "detail_fields": {"hys": ["customfield_45000", "priority"]}, "component_fields": {}})
        self.client.patch(url, {"outstanding_only": False}, format="json")
        self.client.patch(url, {"project_slug": "hys", "detail_field_ids": []}, format="json")
        preferences.refresh_from_db()
        self.assertEqual(preferences.extra_settings["other"], {"keep": True})
        self.assertEqual(self.client.get(url).data["detail_fields"], {"hys": []})
        other = get_user_model().objects.create_user("other-preferences")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(url).data, {"outstanding_only": False, "detail_fields": {}, "component_fields": {}})

    def test_preferences_validate_scope_and_bounded_field_ids(self):
        url = "/api/integrations/jira/watcher/preferences/"
        for payload in ({"detail_field_ids": ["priority"]},
                        {"project_slug": "hys"},
                        {"project_slug": "hys", "detail_field_ids": ["attachment"]},
                        {"project_slug": "hys", "detail_field_ids": ["priority"] * 201}):
            self.assertEqual(self.client.patch(url, payload, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"project_slug": "gokbey", "detail_field_ids": []},
                                          format="json").status_code, 403)
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.patch(url, {"outstanding_only": True}, format="json").status_code, 403)

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_stale_sync_cannot_overwrite_a_newer_record_mutation(self, factory):
        record = self.record()
        def read_after_mutation(**kwargs):
            record.version += 1
            record.save(update_fields=["version"])
            return self.issue()
        factory.return_value.get_issue.side_effect = read_after_mutation
        response = self.client.post(f"/api/integrations/jira/records/{record.id}/status/", {})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "DCC_RECORD_VERSION_CONFLICT")
        record.refresh_from_db()
        self.assertEqual(record.title, "Change")
        self.assertEqual(record.version, 2)

    def test_project_filter_applies_before_pagination(self):
        self.record()
        self.assertEqual(self.client.get("/api/integrations/jira/records/?project_slug=hys").data["count"], 1)
        self.assertEqual(self.client.get("/api/integrations/jira/records/?project_slug=gokbey").data["count"], 0)
        self.assertEqual(self.client.get("/api/integrations/jira/records/?project_slug=unknown").status_code, 400)

    def test_account_preference_save_does_not_erase_watcher_settings(self):
        # Cache a stale preferences instance as overlapping authenticated requests can do.
        self.assertEqual(self.user.preferences.extra_settings, {})
        response = self.client.patch("/api/integrations/jira/watcher/preferences/", {
            "project_slug": "hys", "detail_field_ids": ["priority"]}, format="json")
        self.assertEqual(response.status_code, 200)
        response = self.client.patch("/api/users/preferences/", {"theme": "dark"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["extra_settings"]["watcher"]["detail_fields"], {"hys": ["priority"]})
        self.assertEqual(self.client.get("/api/integrations/jira/watcher/preferences/").data["detail_fields"], {"hys": ["priority"]})

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_component_snapshot_and_none_keep_existing_project_authorization(self, factory):
        record = self.record()
        issue = self.issue()
        issue.fields.components = []
        factory.return_value.get_issue.return_value = issue
        response = self.client.post(f"/api/integrations/jira/records/{record.pk}/status/", {})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["components"], [])
        self.assertEqual(response.data["project_slugs"], ["hys"])
        record.refresh_from_db()
        self.assertEqual(record.components, [])
        self.assertEqual(self.client.get("/api/integrations/jira/records/").data["results"][0]["components"], [])
        ProjectRoleAssignment.objects.filter(user=self.user).delete()
        self.assertEqual(self.client.post(f"/api/integrations/jira/records/{record.pk}/status/", {}).status_code, 404)

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_component_preferences_require_an_authorized_tracked_match_and_preserve_other_preferences(self, factory):
        record = self.record()
        factory.return_value.get_issue.return_value = self.issue()
        self.client.post(f"/api/integrations/jira/records/{record.pk}/status/", {})
        url = "/api/integrations/jira/watcher/preferences/"
        payload = {"record_id": str(record.pk), "component_name": "HYS", "detail_field_ids": ["priority"]}
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["component_fields"], {"component:HYS": ["priority"]})
        self.assertEqual(self.client.patch(url, {**payload, "component_name": "Absent"}, format="json").status_code, 400)
        self.client.patch(url, {"outstanding_only": True}, format="json")
        self.assertEqual(self.client.get(url).data["component_fields"], {"component:HYS": ["priority"]})
        self.client.post("/api/users/preferences/reset/")
        self.assertEqual(self.client.get(url).data["component_fields"], {})
        self.client.force_authenticate(get_user_model().objects.create_user("component-outsider"))
        self.assertEqual(self.client.patch(url, payload, format="json").status_code, 404)

    @patch("integrations.jira.watcher_service.jira_connector_for")
    def test_none_component_preference_round_trip_and_invalid_shapes(self, factory):
        record = self.record()
        issue = self.issue()
        issue.fields.components = []
        factory.return_value.get_issue.return_value = issue
        self.client.post(f"/api/integrations/jira/records/{record.pk}/status/", {})
        url = "/api/integrations/jira/watcher/preferences/"
        payload = {"record_id": str(record.pk), "component_name": None, "detail_field_ids": []}
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["component_fields"], {"none": []})
        for invalid in ({"component_name": "HYS", "detail_field_ids": []},
                        {"record_id": str(record.pk), "detail_field_ids": []},
                        {**payload, "component_name": ""}, {**payload, "detail_field_ids": ["attachment"]}):
            self.assertEqual(self.client.patch(url, invalid, format="json").status_code, 400)
