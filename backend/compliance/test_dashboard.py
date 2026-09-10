"""Regression coverage for project-wide and panel-focused dashboard analytics."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.models import Panel, Project, ProjectRoleAssignment

from .dashboard import build_dashboard
from .models import ComplianceDocument, CoverPage, WorkflowEvent


TODAY = date(2026, 7, 22)


class DashboardTests(TestCase):
    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.other_project = Project.objects.get(slug="aesa")
        self.panel = Panel.objects.create(project=self.project, name="Systems", ata="27")
        self.other_panel = Panel.objects.create(project=self.project, name="Systems", ata="28")
        self.cover = CoverPage.objects.create(project=self.project, number="CP-DASHBOARD")
        self.user = get_user_model().objects.create_user("dashboard-viewer")
        self.client = APIClient()
        self.url = "/api/projects/ozgur/compliance-documents/dashboard/"

    def document(self, name="Document", events=(), **values):
        document = ComplianceDocument.objects.create(
            project=self.project, cover_page=self.cover,
            **{"panel": self.panel, "name": name, "tech_doc_no": name, **values},
        )
        WorkflowEvent.objects.bulk_create([
            WorkflowEvent(
                document=document, sequence=index + 1, status=status,
                effective_date=day, reason="Dashboard fixture", source="import",
            )
            for index, (status, day) in enumerate(events)
        ])
        return document

    def test_all_rows_are_counted_without_per_document_queries(self):
        ComplianceDocument.objects.bulk_create([
            ComplianceDocument(
                project=self.project, cover_page=self.cover, panel=self.panel,
                name=f"Document {index}", status="authority_approved",
            )
            for index in range(205)
        ])
        with self.assertNumQueries(3):
            summary = build_dashboard(self.project, today=TODAY)

        self.assertEqual(summary["total"], 205)
        self.assertEqual(summary["status_counts"], {"authority_approved": 205})
        self.assertEqual(summary["panels"][0]["analytics"]["total"], 205)
        self.assertEqual(summary["risk"]["at_risk_count"], 205)
        self.assertEqual(len(summary["risk"]["priorities"]), 25)
        # Missing workflow evidence must not be reported as an actual delivery.
        self.assertEqual(summary["performance"]["actual"]["filled"], 0)

    def test_panel_scopes_share_all_chart_and_risk_inputs(self):
        self.document(
            "Overdue", status="to_be_issued", ubm_target_date=date(2026, 7, 1),
            next_action_due_date=date(2026, 7, 21), tech_doc_no=None,
            events=[("to_be_issued", date(2026, 7, 1))],
        )
        self.document(
            "In review", panel=self.other_panel, status="authority_review",
            ubm_target_date=date(2026, 7, 2), ubm_delivery_date=date(2026, 7, 3),
            events=[
                ("to_be_issued", date(2026, 7, 2)),
                ("airworthiness_review", date(2026, 7, 3)),
                ("authority_review", date(2026, 7, 5)),
            ],
        )
        summary = build_dashboard(self.project, today=TODAY)
        panels = {panel["id"]: panel["analytics"] for panel in summary["panels"]}
        overdue = panels[str(self.panel.pk)]
        review = panels[str(self.other_panel.pk)]

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["status_counts"], {"to_be_issued": 1, "authority_review": 1})
        self.assertEqual(overdue["chart_status_counts"], {"delayed": 1})
        self.assertEqual(overdue["pending_days"], {"ubm": 21, "aw": 0, "authority": 0})
        self.assertEqual(review["pending_days"], {"ubm": 0, "aw": 2, "authority": 17})
        self.assertEqual(overdue["overdue"], 1)
        self.assertEqual(review["overdue"], 0)
        self.assertEqual(overdue["timeline"]["today"], [{"x": "22.07.2026", "y": 1}])
        self.assertEqual(review["timeline"]["today"], [{"x": "22.07.2026", "y": 0}])
        self.assertEqual(review["performance"]["actual"]["percentage"], 100)
        self.assertEqual(overdue["performance"]["actual"]["percentage"], 0)
        self.assertEqual(overdue["risk"]["priorities"][0]["name"], "Overdue")
        self.assertEqual(review["risk"]["priorities"][0]["name"], "In review")
        self.assertEqual(summary["pending_days"]["authority"], review["pending_days"]["authority"])

    def test_unassigned_archived_and_other_project_documents_are_isolated(self):
        self.document("Unassigned", panel=None)
        self.document("Archived", is_archived=True)
        other_cover = CoverPage.objects.create(project=self.other_project, number="CP-OTHER")
        ComplianceDocument.objects.create(
            project=self.other_project, cover_page=other_cover, name="Other project",
        )

        summary = build_dashboard(self.project, today=TODAY)

        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["archived"], 1)
        self.assertEqual(summary["panels"][0]["id"], "unassigned")
        self.assertEqual(summary["data_quality"]["missing_panel"], 1)
        self.assertEqual(summary["data_quality"]["unknown_status"], 1)
        self.assertEqual(summary["risk"]["priorities"], [])

    def test_empty_dashboard_is_zero_safe(self):
        summary = build_dashboard(self.project, today=TODAY)
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["panels"], [])
        self.assertEqual(summary["risk"]["counts"], {"high": 0, "medium": 0, "low": 0, "none": 0})
        for metric in summary["performance"].values():
            self.assertEqual(metric, {"filled": 0, "empty": 0, "percentage": 0})

    def test_future_targets_and_delivery_dates_do_not_add_elapsed_time(self):
        self.document(
            status="to_be_issued", ubm_target_date=date(2026, 8, 1),
            ubm_delivery_date=date(2026, 8, 2),
            events=[("to_be_issued", date(2026, 8, 1))],
        )
        summary = build_dashboard(self.project, today=TODAY)
        self.assertEqual(summary["chart_status_counts"], {"to_be_issued": 1})
        self.assertEqual(summary["pending_days"]["ubm"], 0)
        self.assertEqual(summary["data_quality"]["out_of_order_dates"], 0)
        self.assertIsNone(summary["timeline"]["last_actual"])
        self.assertEqual(summary["performance"]["actual"]["filled"], 0)

    def test_invalid_event_order_is_reported_without_negative_pending_days(self):
        self.document(
            events=[
                ("airworthiness_review", date(2026, 7, 5)),
                ("authority_review", date(2026, 7, 3)),
            ],
        )
        summary = build_dashboard(self.project, today=TODAY)
        self.assertEqual(summary["data_quality"]["out_of_order_dates"], 1)
        self.assertEqual(summary["pending_days"]["aw"], 0)
        self.assertEqual(summary["pending_days"]["authority"], 19)

    def test_dashboard_preserves_project_authorization_and_response_privacy(self):
        self.document(tech_doc_no=None, notes="Internal notes", path="private/path")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        ProjectRoleAssignment.objects.create(
            project=self.project, user=self.user, domain="compliance", role="viewer",
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["project"], self.project.slug)
        self.assertEqual(response.data["risk"]["at_risk_count"], 1)
        for private_field in ("notes", "path", "actor_username", "tech_doc_no", "workflow_events"):
            self.assertNotIn(f'"{private_field}"', response.content.decode())
        self.assertEqual(
            self.client.get(self.url.replace("ozgur", "aesa")).status_code, 403,
        )
