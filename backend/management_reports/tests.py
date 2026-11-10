"""Management report access, snapshot and comparison regression tests."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import Mock, patch
from types import ModuleType

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment
from compliance.models import ComplianceDocument, CoverPage, WorkflowEvent, ReviewTask
from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext
from management_reports.models import ReportSnapshot


class ManagementReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("report-owner")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.project = Project.objects.get(slug="ozgur")
        self.grant(self.user, "ozgur")

    def grant(self, user, slug):
        return ProjectRoleAssignment.objects.create(
            user=user, project=Project.objects.get(slug=slug), domain="compliance", role="viewer",
        )

    def document(self, project_slug="ozgur", cover_page_no="CP-TEST", status_flow=(), **values):
        from datetime import date

        project = Project.objects.get(slug=project_slug)
        cover, _ = CoverPage.objects.get_or_create(project=project, number=cover_page_no)
        if status_flow:
            values.setdefault("target_date", date.fromisoformat(status_flow[0]["date"]))
            values.setdefault("status", status_flow[-1]["status"])
            if values["status"] == "authority_approved":
                values.setdefault("release_date", date.fromisoformat(status_flow[-1]["date"]))
        document = ComplianceDocument.objects.create(project=project, cover_page=cover, **values)
        WorkflowEvent.objects.bulk_create([
            WorkflowEvent(document=document, sequence=index + 1, status=entry["status"],
                          effective_date=entry["date"], reason="Report fixture", source="import")
            for index, entry in enumerate(status_flow)
        ])
        return document

    def create_report(self, **overrides):
        data = {"project_slugs": ["ozgur"], "title": "Weekly", "management_note": "Decision request"}
        data.update(overrides)
        return self.client.post("/api/management-reports/reports/", data, format="json")

    def test_authentication_and_authorized_options(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get("/api/management-reports/options/").status_code, (401, 403))
        self.client.force_authenticate(self.user)
        projects = self.client.get("/api/management-reports/options/").data["projects"]
        self.assertEqual([item["slug"] for item in projects], ["ozgur"])
        self.assertEqual(set(projects[0]), {"slug", "display_name"})

    def test_validates_scope_and_rejects_server_controlled_fields(self):
        for scope in ([], ["ozgur", "ozgur"], ["unknown"], ["hurkus"], ["ozgur"] * 100):
            self.assertEqual(self.create_report(project_slugs=scope).status_code, 400)
        self.assertEqual(self.create_report(project_slugs=["piku"]).status_code, 403)
        for field in ("payload", "captured_at", "owner", "totals", "schema_version"):
            self.assertEqual(self.create_report(**{field: "injected"}).status_code, 400)
        self.assertEqual(self.create_report(title="x" * 121).status_code, 400)
        self.assertEqual(self.create_report(management_note="x" * 2001).status_code, 400)

    def test_weighted_totals_snapshot_immutability_and_priority_context(self):
        self.grant(self.user, "piku")
        self.document(name="Approved", cover_page_no="CP-1", status_flow=[
            {"status": "to_be_issued", "date": "2020-01-01"},
            {"status": "authority_approved", "date": "2020-01-02"},
        ])
        for index in range(3):
            self.document(project_slug="piku", name=f"Pending {index}", cover_page_no=f"CP-P-{index}",
                status_flow=[{"status": "to_be_issued", "date": "2020-01-01"}], owner=self.user)
        response = self.create_report(project_slugs=["piku", "ozgur"])
        self.assertEqual(response.status_code, 201, response.data)
        report = response.data["report"]
        self.assertEqual(report["project_slugs"], ["ozgur", "piku"])
        self.assertEqual(report["totals"]["document_count"], 4)
        self.assertEqual(report["totals"]["approval_percentage"], 25.0)
        self.assertEqual(report["totals"]["issued_count"], 1)
        self.assertEqual(report["totals"]["schedule_variance"], -3)
        self.assertTrue(report["priorities"])
        self.assertIn("owner", report["priorities"][0])
        self.assertIn("next_action_due_date", report["priorities"][0])
        self.document(name="Added later", cover_page_no="CP-2")
        detail = self.client.get(f'/api/management-reports/reports/{report["id"]}/')
        self.assertEqual(detail.data["report"]["totals"], report["totals"])
        self.assertEqual(self.client.patch(f'/api/management-reports/reports/{report["id"]}/', {}, format="json").status_code, 405)

    def test_empty_overview_and_missing_baseline(self):
        response = self.client.get("/api/management-reports/overview/", {"projects": "ozgur"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["report"]["id"])
        self.assertEqual(response.data["report"]["totals"]["approval_percentage"], 0)
        self.assertEqual(response.data["comparison"], {"available": False, "baseline": None, "elapsed_days": None, "deltas": None})

    def test_owner_isolation_and_revoked_permissions_for_every_read(self):
        report_id = self.create_report().data["report"]["id"]
        other = get_user_model().objects.create_user("another-owner")
        self.grant(other, "ozgur")
        self.client.force_authenticate(other)
        for suffix in ("", "pdf/"):
            self.assertEqual(self.client.get(f"/api/management-reports/reports/{report_id}/{suffix}").status_code, 404)
        self.assertEqual(self.client.get("/api/management-reports/reports/").data["count"], 0)
        ProjectRoleAssignment.objects.filter(user=self.user).delete()
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        for suffix in ("", "pdf/"):
            self.assertEqual(self.client.get(f"/api/management-reports/reports/{report_id}/{suffix}").status_code, 403)
        self.assertEqual(self.client.get("/api/management-reports/reports/").data["count"], 0)

    def test_previous_calendar_week_and_explicit_baseline_validation(self):
        monday = datetime(2026, 10, 26, 12, tzinfo=dt_timezone.utc)
        with patch("management_reports.services.timezone.now", return_value=monday - timedelta(days=8)):
            too_old = self.create_report().data["report"]["id"]
        with patch("management_reports.services.timezone.now", return_value=monday - timedelta(days=1)):
            previous = self.create_report().data["report"]["id"]
        with patch("management_reports.services.timezone.now", return_value=monday):
            current = self.create_report().data
        self.assertEqual(current["comparison"]["baseline"]["id"], previous)
        current_id = current["report"]["id"]
        explicit = self.client.get(f"/api/management-reports/reports/{current_id}/", {"baseline": too_old})
        self.assertEqual(explicit.status_code, 200)
        self.assertEqual(explicit.data["comparison"]["baseline"]["id"], too_old)
        self.assertEqual(explicit.data["comparison"]["deltas"]["document_count"], 0)
        self.assertEqual(self.client.get(f"/api/management-reports/reports/{previous}/", {"baseline": current_id}).status_code, 400)
        ReportSnapshot.objects.filter(pk=too_old).update(schema_version=2)
        self.assertEqual(self.client.get(f"/api/management-reports/reports/{current_id}/", {"baseline": too_old}).status_code, 400)
        self.assertEqual(self.client.get(f"/api/management-reports/reports/{current_id}/", {"baseline": "invalid"}).status_code, 400)

    def test_pagination_scope_and_pdf_delegation(self):
        first = self.create_report().data["report"]
        snapshot = ReportSnapshot.objects.get(pk=first["id"])
        ReportSnapshot.objects.bulk_create([ReportSnapshot(owner=self.user, project_slugs=snapshot.project_slugs,
            scope_key=snapshot.scope_key, captured_at=snapshot.captured_at, week_start=snapshot.week_start,
            payload=snapshot.payload) for _ in range(20)])
        listing = self.client.get("/api/management-reports/reports/")
        self.assertEqual(listing.data["count"], 21)
        self.assertEqual(len(listing.data["results"]), 20)
        self.assertIsNotNone(listing.data["next"])
        self.assertEqual(self.client.get("/api/management-reports/reports/", {"projects": "piku"}).status_code, 403)
        pdf_module = ModuleType("management_reports.pdf")
        builder = pdf_module.build_report_pdf = Mock(return_value=b"%PDF-example")
        with patch.dict("sys.modules", {"management_reports.pdf": pdf_module}):
            pdf = self.client.get(f'/api/management-reports/reports/{first["id"]}/pdf/')
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertEqual(pdf.content, b"%PDF-example")
        self.assertEqual(builder.call_args.args[0]["id"], first["id"])

    def test_default_baseline_is_only_previous_week_and_latest_matching_capture(self):
        monday = datetime(2026, 10, 26, 12, tzinfo=dt_timezone.utc)
        with patch("management_reports.services.timezone.now", return_value=monday - timedelta(days=8)):
            self.create_report()
        with patch("management_reports.services.timezone.now", return_value=monday):
            self.assertFalse(self.create_report().data["comparison"]["available"])
        with patch("management_reports.services.timezone.now", return_value=monday - timedelta(days=4)):
            self.create_report()
        with patch("management_reports.services.timezone.now", return_value=monday - timedelta(days=1)):
            latest_previous = self.create_report().data["report"]["id"]
        with patch("management_reports.services.timezone.now", return_value=monday + timedelta(days=2)):
            report = self.create_report().data
        self.assertEqual(report["comparison"]["baseline"]["id"], latest_previous)
        self.assertEqual(report["report"]["week_start"], "2026-10-26")

    def test_baseline_scope_ownership_and_revoked_scope_are_rejected(self):
        self.grant(self.user, "piku")
        baseline = self.create_report(project_slugs=["ozgur", "piku"]).data["report"]
        current = self.create_report().data["report"]
        url = f'/api/management-reports/reports/{current["id"]}/'
        self.assertEqual(self.client.get(url, {"baseline": baseline["id"]}).status_code, 400)
        other = get_user_model().objects.create_user("baseline-other-owner")
        ReportSnapshot.objects.filter(pk=baseline["id"]).update(owner=other)
        self.assertEqual(self.client.get(url, {"baseline": baseline["id"]}).status_code, 404)
        ReportSnapshot.objects.filter(pk=baseline["id"]).update(owner=self.user)
        ProjectRoleAssignment.objects.filter(user=self.user, project__slug="piku").delete()
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get(url, {"baseline": baseline["id"]}).status_code, 403)
        self.assertEqual(self.client.get("/api/management-reports/reports/").data["count"], 1)

    def test_week_boundary_uses_local_monday_not_utc_sunday(self):
        # Istanbul's Monday begins while UTC is still Sunday.
        instant = datetime(2026, 10, 25, 22, 30, tzinfo=dt_timezone.utc)
        with self.settings(TIME_ZONE="Europe/Istanbul"):
            with patch("management_reports.services.timezone.now", return_value=instant):
                response = self.create_report()
        self.assertEqual(response.data["report"]["week_start"], "2026-10-26")

    def test_api_error_contract_and_empty_scope_do_not_save_reports(self):
        response = self.create_report(project_slugs=[])
        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.data)
        self.assertIn("detail", response.data)
        self.assertIn("request_id", response.data)
        self.assertEqual(ReportSnapshot.objects.count(), 0)
        for query in ({}, {"projects": "ozgur,"}, {"projects": "ozgur,ozgur"}):
            self.assertEqual(self.client.get("/api/management-reports/overview/", query).status_code, 400)

    def test_real_pdf_download_has_report_content_and_access_is_rechecked(self):
        from io import BytesIO
        from pypdf import PdfReader

        report = self.create_report(title="Yönetim Özeti", management_note="Türkçe karar isteği").data["report"]
        url = f'/api/management-reports/reports/{report["id"]}/pdf/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
        self.assertIn("Yönetim Özeti", text)
        self.assertIn("Türkçe karar isteği", text)
        other = get_user_model().objects.create_user("pdf-other-owner")
        self.grant(other, "ozgur")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(url).status_code, 404)
        ProjectRoleAssignment.objects.filter(user=self.user).delete()
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_priority_document_disappearing_during_capture_does_not_break_report(self):
        from compliance.dashboard import build_dashboard

        document = self.document(name="Concurrent", cover_page_no="CP-CONCURRENT",
            status_flow=[{"status": "to_be_issued", "date": "2020-01-01"}])
        dashboard = build_dashboard(self.project)
        document.delete()
        with patch("management_reports.services.build_dashboard", return_value=dashboard):
            response = self.client.get("/api/management-reports/overview/", {"projects": "ozgur"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["report"]["priorities"], [])

    def test_capture_rolls_back_when_envelope_cannot_be_built(self):
        from rest_framework.exceptions import ValidationError

        with patch("management_reports.views.compare_report", side_effect=ValidationError("Comparison failed")):
            response = self.create_report()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ReportSnapshot.objects.count(), 0)

    def test_group_roles_enabled_projects_and_business_names(self):
        group = Group.objects.create(name="report-viewers")
        self.user.groups.add(group)
        project = Project.objects.get(slug="piku")
        project.name = "Portfolio display name"
        project.save(update_fields=["name"])
        ProjectRoleAssignment.objects.create(group=group, project=project, domain="compliance", role="viewer")
        options = self.client.get("/api/management-reports/options/").data["projects"]
        self.assertIn({"slug": "piku", "display_name": "Portfolio display name"}, options)
        report_id = self.create_report(project_slugs=["ozgur", "piku"]).data["report"]["id"]
        project.enabled = False
        project.save(update_fields=["enabled"])
        self.assertEqual(self.client.get(f"/api/management-reports/reports/{report_id}/").status_code, 400)
        self.assertEqual(self.client.get("/api/management-reports/reports/").data["count"], 0)

    def test_full_catalog_can_be_captured_and_history_query_is_bounded(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        options = self.client.get("/api/management-reports/options/").data["projects"]
        slugs = [item["slug"] for item in options]
        self.assertGreater(len(slugs), 8)
        response = self.create_report(project_slugs=slugs)
        self.assertEqual(response.status_code, 201, response.data)
        with CaptureQueriesContext(connection) as queries:
            history = self.client.get("/api/management-reports/reports/")
        self.assertEqual(history.data["count"], 1)
        self.assertLess(len(queries), 8)
        self.assertLess(max(len(item["sql"]) for item in queries), 10000)

    def test_operational_counts_exclude_archived_and_other_project_documents(self):
        from datetime import timedelta
        from django.utils import timezone

        today = timezone.localdate()
        active = self.document(name="Active", next_action_due_date=today - timedelta(days=1))
        self.document(name="Soon", next_action_due_date=today + timedelta(days=7), owner=self.user)
        archived = self.document(name="Archived", is_archived=True)
        other = self.document(project_slug="piku", name="Other")
        for document in (active, archived, other):
            ReviewTask.objects.create(document=document, kind="review", assignee=self.user,
                assignee_username=self.user.username, requested_by=self.user,
                requested_by_username=self.user.username, source_version=1, request_note="Review")
        overview = self.client.get("/api/management-reports/overview/", {"projects": "ozgur"})
        totals = overview.data["report"]["totals"]
        self.assertEqual(totals["document_count"], 2)
        self.assertEqual(totals["action_overdue_count"], 1)
        self.assertEqual(totals["action_due_soon_count"], 1)
        self.assertEqual(totals["unassigned_count"], 1)
        self.assertEqual(totals["pending_review_count"], 1)

    def test_session_capture_requires_csrf_and_has_no_legacy_route(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        data = {"project_slugs": ["ozgur"], "title": "Weekly"}
        self.assertEqual(client.post("/api/management-reports/reports/", data, format="json").status_code, 403)
        client.cookies["csrftoken"] = "a" * 32
        response = client.post("/api/management-reports/reports/", data, format="json", HTTP_X_CSRFTOKEN="a" * 32)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(client.get("/management-reports/options/").status_code, 404)
