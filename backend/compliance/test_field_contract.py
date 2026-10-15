"""Regression coverage for the canonical document fields and import boundaries."""

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment

from .compdoc_import import map_headers
from .imports import IMPORT_FIELDS


class CanonicalImportFieldTests(SimpleTestCase):
    def test_legacy_source_headers_map_to_canonical_targets(self):
        self.assertEqual(
            map_headers([
                "tech_doc_no", "tech_doc_issue", "ubm_target_date",
                "ubm_revised_target_date", "ubm_delivery_date",
            ], IMPORT_FIELDS),
            {
                "tech_doc_no": "number", "tech_doc_issue": "issue",
                "ubm_target_date": "target_date",
                "ubm_revised_target_date": "revised_target_date",
                "ubm_delivery_date": "release_date",
            },
        )

    def test_removed_source_columns_cannot_capture_primary_fields(self):
        columns = [
            "tech_doc_no_2", "Tech Doc No 2", "tech_doc_issue_2", "Tech Doc Issue 2",
            "delivered_tech_doc_issue", "Delivered Issue", "Delivery Issue",
            "delivered_tech_doc_issue_2", "Delivered Tech Doc Issue 2",
            "number", "issue", "release_date",
        ]
        self.assertEqual(map_headers(columns, IMPORT_FIELDS), {
            "number": "number", "issue": "issue", "release_date": "release_date",
        })


class CanonicalDocumentApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.get(slug="ozgur")
        cls.user = get_user_model().objects.create_user("field-editor")
        ProjectRoleAssignment.objects.create(
            project=cls.project, user=cls.user, domain="compliance", role="editor",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = "/api/projects/ozgur/compliance-documents/"

    def test_canonical_fields_round_trip_with_distinct_cover_page_fields(self):
        payload = {
            "name": "Canonical document", "cover_page": {"number": "CP-123", "issue": "C"},
            "number": "TD-123", "issue": "B", "target_date": "2026-10-01",
            "revised_target_date": "2026-11-01", "release_date": "2026-09-01",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        for field, value in payload.items():
            if field != "cover_page":
                self.assertEqual(response.data.get(field), value, field)
        self.assertEqual(response.data["cover_page"]["number"], "CP-123")
        self.assertEqual(response.data["cover_page"]["issue"], "C")
        for query in ({"search": "TD-123"}, {"number": "TD-123"},
                      {"issue": "B"}, {"revised_target_date": "2026-11-01"},
                      {"ordering": "-release_date"}):
            listed = self.client.get(self.url, query)
            self.assertEqual(listed.status_code, 200, listed.data)
            self.assertEqual(listed.data["count"], 1)
        detail = f'{self.url}{response.data["id"]}/'
        updated = self.client.patch(detail, {
            "version": response.data["version"], "issue": "D", "release_date": None,
        }, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["issue"], "D")
        self.assertIsNone(updated.data["release_date"])
        self.assertEqual(self.client.patch(detail, {
            "version": 1, "number": "STALE",
        }, format="json").status_code, 409)

    def test_field_metadata_exposes_only_current_document_fields(self):
        response = self.client.get(f"{self.url}fields/")
        self.assertEqual(response.status_code, 200, response.data)
        fields = {field["key"]: field for field in response.data["fields"]}
        self.assertTrue({"number", "issue", "target_date", "revised_target_date", "release_date"} <= fields.keys())
        self.assertFalse({
            "tech_doc_no", "tech_doc_issue", "ubm_target_date", "ubm_revised_target_date",
            "ubm_delivery_date", "tech_doc_no_2", "tech_doc_issue_2",
            "delivered_tech_doc_issue", "delivered_tech_doc_issue_2",
        } & fields.keys())
        self.assertEqual(fields["release_date"]["filter_kind"], "date")
