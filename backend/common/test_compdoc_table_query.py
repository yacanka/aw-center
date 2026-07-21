"""Remote compliance-document table query contract tests."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from common.compdoc_import_test_utils import grant_model_permissions
from projects.ozgur.models import CompDoc


class CompDocTableQueryTests(TestCase):
    """Verify metadata, projections, filters, and ordering use database fields."""

    def setUp(self):
        """Create permissioned API client and representative workflow states."""

        self.user = get_user_model().objects.create_user("table-user", password="StrongPass!123")
        grant_model_permissions(self.user, CompDoc, "view")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.delayed = self._document(
            "Alpha Manual", "Structures", [{"status": "to_be_issued", "date": "01.01.2020"}]
        )
        self.review = self._document(
            "Bravo Report",
            "Systems",
            [
                {"status": "to_be_issued", "date": "01.01.2030"},
                {"status": "authority_review", "date": "15.01.2030"},
            ],
        )
        self.scheduled = self._document(
            "Delta Plan", "Systems", [{"status": "to_be_issued", "date": "01.01.2030"}]
        )
        self._document("Charlie Note", "Structures", [])

    def test_metadata_response_identifies_server_schema(self):
        """Schema endpoint declares its project and versioned field capabilities."""

        response = self.client.get("/ozgur/compdocs/fields/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["project"], "ozgur")
        self.assertGreaterEqual(response.data["schema_version"], 2)
        self.assertTrue(any(field["key"] == "status" for field in response.data["fields"]))

    def test_model_save_projects_workflow_fields(self):
        """Workflow JSON is projected into stable typed database columns."""

        self.assertEqual(self.review.status, "authority_review")
        self.assertEqual(self.review.ubm_target_date, date(2030, 1, 1))
        self.assertEqual(self.review.ubm_delivery_date, date(2030, 1, 15))

    def test_text_multi_select_and_date_filters(self):
        """Remote query supports text, repeated choices, and date operators."""

        text = self._results({"name": "report"})
        panels = self._results({"panel": ["Structures", "Systems"]})
        dates = self._results({"ubm_target_date__gte": "2029-01-01"})

        self.assertEqual([row["name"] for row in text], ["Bravo Report"])
        self.assertEqual(len(panels), 4)
        self.assertEqual({row["name"] for row in dates}, {"Delta Plan", "Bravo Report"})

    def test_delayed_filter_and_database_ordering(self):
        """Virtual delayed status and configured ordering work across pagination."""

        delayed = self._results({"status": "delayed"})
        pending = self._results({"status": "to_be_issued"})
        ordered = self._results({"ordering": "name"})

        self.assertEqual([row["id"] for row in delayed], [str(self.delayed.id)])
        self.assertEqual([row["id"] for row in pending], [str(self.scheduled.id)])
        self.assertEqual([row["name"] for row in ordered], [
            "Alpha Manual",
            "Bravo Report",
            "Charlie Note",
            "Delta Plan",
        ])

    def test_rejects_ordering_outside_server_schema(self):
        """Unknown ordering keys fail explicitly instead of reaching the ORM."""

        response = self.client.get("/ozgur/compdocs/", {"ordering": "status_flow"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("ordering", response.data["errors"])

    def test_rejects_invalid_date_with_field_error(self):
        """Malformed dates return the standard recoverable validation contract."""

        response = self.client.get(
            "/ozgur/compdocs/", {"ubm_target_date__gte": "not-a-date"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ubm_target_date", response.data["errors"])

    def test_derived_fields_are_read_only_in_writes(self):
        """Clients cannot forge indexed workflow projections independently of JSON."""

        grant_model_permissions(self.user, CompDoc, "add", "change")
        response = self.client.post(
            "/ozgur/compdocs/",
            {
                "name": "Projection Test",
                "cover_page_no": "CP-PROJECTION",
                "status": "authority_approved",
                "ubm_target_date": "2099-02-02",
                "status_flow": [{"status": "to_be_issued", "date": "01.01.2099"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "to_be_issued")
        self.assertEqual(response.data["ubm_target_date"], "2099-01-01")

    def _results(self, query):
        response = self.client.get("/ozgur/compdocs/", query)
        self.assertEqual(response.status_code, 200)
        return response.data["results"]

    @staticmethod
    def _document(name, panel, status_flow):
        return CompDoc.objects.create(
            name=name,
            panel=panel,
            cover_page_no=f"CP-{name[:5].upper()}",
            status_flow=status_flow,
        )
