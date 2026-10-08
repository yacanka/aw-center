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
        # The project vocabulary adds one bounded query, independent of document count.
        with self.assertNumQueries(4):
            summary = build_dashboard(self.project, today=TODAY)

        self.assertEqual(summary["total"], 205)
        self.assertEqual(summary["status_counts"], {"authority_approved": 205})
        self.assertEqual(summary["panels"][0]["analytics"]["total"], 205)
        self.assertEqual(summary["risk"]["at_risk_count"], 205)
        self.assertEqual(len(summary["risk"]["priorities"]), 25)
        self.assertEqual(summary["panel_groups"][0]["analytics"]["risk"], summary["risk"])
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

    def test_named_panel_groups_use_complete_analytics_across_ata_chapters(self):
        self.document(
            "Overdue", status="to_be_issued", ubm_target_date=date(2026, 7, 1),
            next_action_due_date=date(2026, 7, 21),
            events=[("to_be_issued", date(2026, 7, 1))],
        )
        self.document(
            "Approved", panel=self.other_panel, status="authority_approved",
            ubm_target_date=date(2026, 7, 2), ubm_delivery_date=date(2026, 7, 3),
            events=[("authority_approved", date(2026, 7, 3))],
        )
        self.document("Archived", is_archived=True)
        with self.assertNumQueries(4):
            summary = build_dashboard(self.project, today=TODAY)

        self.assertEqual(len(summary["panels"]), 2)
        self.assertEqual(len(summary["panel_groups"]), 1)
        group = summary["panel_groups"][0]
        self.assertEqual(group["panel"], "Systems")
        self.assertEqual(group["ata"], "27, 28")
        self.assertEqual(group["analytics"], {
            key: summary[key] for key in group["analytics"]
        })
        self.assertEqual(group["analytics"]["performance"]["approved"]["percentage"], 50)
        self.assertEqual(group["analytics"]["timeline"]["today"], [{"x": "22.07.2026", "y": 1}])

    def test_named_panel_groups_isolate_other_names_and_unassigned_documents(self):
        self.document("Systems")
        structures = Panel.objects.create(project=self.project, name="Structures", ata="53")
        self.document("Structures", panel=structures)
        self.document("Unassigned", panel=None)
        summary = build_dashboard(self.project, today=TODAY)
        groups = {group["panel"]: group for group in summary["panel_groups"]}
        self.assertEqual(set(groups), {"Systems", "Structures", "Unassigned"})
        self.assertEqual(groups["Unassigned"]["ata"], "")
        for group in groups.values():
            self.assertEqual(group["analytics"]["total"], 1)

    def test_empty_dashboard_is_zero_safe(self):
        summary = build_dashboard(self.project, today=TODAY)
        self.assertEqual(summary["cat_counts"], {})
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["panels"], [])
        self.assertEqual(summary["panel_groups"], [])
        self.assertEqual(summary["risk"]["counts"], {"high": 0, "medium": 0, "low": 0, "none": 0})
        for metric in summary["performance"].values():
            self.assertEqual(metric, {"filled": 0, "empty": 0, "percentage": 0})

    def test_cat_distribution_preserves_scope_and_counts_missing_values(self):
        self.document("CAT A", cat="A")
        self.document("CAT A second", cat="A", panel=self.other_panel)
        self.document("CAT B", cat="B", panel=self.other_panel)
        self.document("Missing CAT", cat=None)
        self.document("Blank CAT", cat="  ", panel=None)
        self.document("Archived CAT", cat="C", is_archived=True)
        other_cover = CoverPage.objects.create(project=self.other_project, number="CP-CAT-OTHER")
        ComplianceDocument.objects.create(
            project=self.other_project, cover_page=other_cover, name="Other CAT", cat="C",
        )

        with self.assertNumQueries(4):
            summary = build_dashboard(self.project, today=TODAY)

        self.assertEqual(summary["cat_counts"], {"A": 2, "B": 1, "": 2})
        panels = {panel["id"]: panel["analytics"] for panel in summary["panels"]}
        self.assertEqual(panels[str(self.panel.pk)]["cat_counts"], {"A": 1, "": 1})
        self.assertEqual(panels[str(self.other_panel.pk)]["cat_counts"], {"A": 1, "B": 1})
        groups = {group["panel"]: group["analytics"] for group in summary["panel_groups"]}
        self.assertEqual(groups["Systems"]["cat_counts"], {"A": 2, "B": 1, "": 1})
        self.assertEqual(groups["Unassigned"]["cat_counts"], {"": 1})

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
        self.assertEqual(summary["performance"]["actual"]["filled"], 1)

    def test_revised_target_controls_delay_and_scheduled_timeline(self):
        self.document(
            status="to_be_issued",
            ubm_target_date=date(2026, 7, 1),
            ubm_revised_target_date=date(2026, 8, 1),
        )

        summary = build_dashboard(self.project, today=TODAY)

        self.assertEqual(summary["chart_status_counts"], {"expected": 1})
        self.assertEqual(summary["performance"]["scheduled"]["filled"], 0)

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

    def test_publication_depends_on_delivery_and_groups_unissued_by_current_target(self):
        self.document("Late review", status="authority_review", ubm_target_date=date(2026, 7, 1), moc="1")
        self.document("Due today", ubm_target_date=TODAY, moc="1")
        self.document("Replanned", ubm_target_date=date(2026, 7, 1),
                      ubm_revised_target_date=date(2026, 8, 1), moc="2")
        self.document("No target", status="authority_approved", moc=None)
        self.document("Delivered", status="custom_review", ubm_delivery_date=TODAY, moc="3")
        self.document("Future delivery", status="to_be_issued", ubm_delivery_date=date(2026, 8, 2))
        self.document("Archived", is_archived=True, moc="4")
        with self.assertNumQueries(4):
            summary = build_dashboard(self.project, today=TODAY)
        self.assertEqual(summary["publication"], {
            "issued": {"total": 2, "status_counts": {"custom_review": 1, "to_be_issued": 1}},
            "not_issued": {"total": 4, "status_counts": {"delayed": 1, "expected": 2, "missing_target": 1}},
        })
        self.assertEqual(summary["unissued_moc_counts"], {"1": 2, "2": 1, "": 1})
        self.assertEqual(summary["performance"]["actual"]["filled"], 2)
        self.assertEqual(summary["performance"]["scheduled"]["filled"], 2)
        self.assertEqual(summary["panels"][0]["analytics"]["publication"], summary["publication"])
        self.assertEqual(summary["panel_groups"][0]["analytics"]["unissued_moc_counts"], summary["unissued_moc_counts"])
        # Dashboard projections must not change canonical workflow status counts.
        self.assertEqual(summary["status_counts"]["authority_review"], 1)

    def test_burndown_separates_original_and_revised_plan_with_fallback(self):
        self.document("Revised", ubm_target_date=date(2026, 7, 1),
                      ubm_revised_target_date=date(2026, 8, 1), ubm_delivery_date=date(2026, 7, 5))
        self.document("Original", ubm_target_date=date(2026, 7, 3))
        summary = build_dashboard(self.project, today=TODAY)
        self.assertEqual(summary["timeline"]["scheduled"], [
            {"x": "01.07.2026", "y": 1}, {"x": "03.07.2026", "y": 0},
        ])
        self.assertEqual(summary["timeline"]["revised_scheduled"], [
            {"x": "03.07.2026", "y": 1}, {"x": "01.08.2026", "y": 0},
        ])
        self.assertEqual(summary["performance"]["scheduled"]["filled"], 1)
        self.assertEqual(summary["timeline"]["today"], [{"x": "22.07.2026", "y": 1}])

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
