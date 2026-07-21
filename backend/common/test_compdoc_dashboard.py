"""Compliance-document dashboard aggregation and API tests."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from common.compdoc_dashboard import build_compdoc_dashboard
from common.cover_page_models import CoverPage
from projects.ozgur.models import CompDoc

from .compdoc_import_test_utils import grant_model_permissions


class CompDocDashboardAggregationTests(TestCase):
    """Verify complete, resilient project analytics."""

    def test_aggregates_all_rows_beyond_list_page_limit(self):
        """Dashboard counts the project, not only the first API page."""

        cover_page = CoverPage.objects.create(project_slug="ozgur", number="CP-DASH")
        CompDoc.objects.bulk_create(
            [self._document(cover_page, index) for index in range(205)]
        )

        summary = self._summary()

        self.assertEqual(summary["document_count"], 205)
        self.assertEqual(summary["status_counts"]["authority_approved"], 205)
        self.assertEqual(summary["panels"][0]["total"], 205)

    def test_reports_malformed_flow_without_failing_dashboard(self):
        """Malformed workflow data is isolated and surfaced as a quality signal."""

        cover_page = CoverPage.objects.create(project_slug="ozgur", number="CP-BAD")
        CompDoc.objects.bulk_create(
            [
                self._document(cover_page, 1, status_flow={"status": "bad"}),
                self._document(
                    cover_page,
                    2,
                    status_flow=[{"status": "to_be_issued", "date": "not-a-date"}],
                ),
            ]
        )

        summary = self._summary()

        self.assertEqual(summary["status_counts"]["unknown"], 1)
        self.assertEqual(summary["status_counts"]["to_be_issued"], 1)
        self.assertEqual(summary["data_quality"]["invalid_status_flow"], 1)
        self.assertEqual(summary["data_quality"]["invalid_dates"], 1)

    def test_computes_delay_timeline_and_safe_zero_percentages(self):
        """Overdue targets and empty projects produce deterministic metrics."""

        cover_page = CoverPage.objects.create(project_slug="ozgur", number="CP-DATE")
        CompDoc.objects.bulk_create(
            [
                self._document(
                    cover_page,
                    1,
                    status_flow=[{"status": "to_be_issued", "date": "01.01.2026"}],
                )
            ]
        )

        summary = self._summary(today=date(2026, 1, 11))
        empty = build_compdoc_dashboard(CompDoc.objects.none().values("panel", "status_flow"))

        self.assertEqual(summary["status_counts"]["delayed"], 1)
        self.assertEqual(summary["pending_days"]["ubm"], 10)
        self.assertEqual(empty["performance"]["approved"]["percentage"], 0)

    def _summary(self, today=None):
        return build_compdoc_dashboard(
            CompDoc.objects.values("panel", "status_flow"), today=today
        )

    @staticmethod
    def _document(cover_page, index, status_flow=None):
        return CompDoc(
            name=f"Document {index}",
            cover_page=cover_page,
            cover_page_no=cover_page.number,
            panel="Panel A",
            status_flow=status_flow
            if status_flow is not None
            else [{"status": "authority_approved", "date": "01.01.2026"}],
        )


class CompDocDashboardApiTests(TestCase):
    """Verify dashboard authorization and query behavior."""

    def setUp(self):
        """Create an authenticated user without project access."""

        self.user = get_user_model().objects.create_user("dashboard-user", password="Pass!123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_requires_project_view_permission(self):
        """Dashboard cannot bypass the CompDoc read boundary."""

        denied = self.client.get("/ozgur/compdocs/dashboard/")
        grant_model_permissions(self.user, CompDoc, "view")
        allowed = self.client.get("/ozgur/compdocs/dashboard/")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data["document_count"], 0)

    def test_dashboard_uses_one_document_query(self):
        """Aggregation remains constant-query as document volume grows."""

        grant_model_permissions(self.user, CompDoc, "view")

        with self.assertNumQueries(3):
            response = self.client.get("/ozgur/compdocs/dashboard/")

        self.assertEqual(response.status_code, 200)
