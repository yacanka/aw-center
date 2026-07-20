"""Regression tests for CompDoc optimistic concurrency."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from projects.ozgur.models import CompDoc

from .compdoc_import_test_utils import grant_model_permissions


class CompdocConcurrencyTests(TestCase):
    """Verify current history exposure and stale-write rejection."""

    def setUp(self):
        """Create one authorized editor and representative document."""

        self.user = get_user_model().objects.create_user(
            "compdoc-editor", password="StrongPass!123"
        )
        grant_model_permissions(self.user, CompDoc, "view", "change")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.document = CompDoc.objects.create(name="Flight Manual", cover_page_no="CC-1")
        self.path = f"/ozgur/compdocs/{self.document.pk}/"

    def test_list_and_detail_expose_current_history_without_n_plus_one(self):
        """Paginated rows and details include the same server-derived version."""

        CompDoc.objects.create(name="Second Manual", cover_page_no="CC-2")
        with self.assertNumQueries(4):
            listed = self.client.get("/ozgur/compdocs/")
        detailed = self.client.get(self.path)

        versions = {row["source_history_id"] for row in listed.data["results"]}
        self.assertEqual(len(versions), 2)
        self.assertEqual(
            detailed.data["source_history_id"], self.document.history.first().history_id
        )

    def test_missing_and_stale_versions_fail_without_writing(self):
        """Mandatory and superseded versions cannot silently overwrite newer data."""

        opened_version = self.current_version()
        missing = self.client.patch(self.path, {"name": "Missing version"})
        self.document.name = "Another editor's update"
        self.document.save(update_fields=["name"])
        stale = self.client.patch(
            self.path, {"name": "Stale overwrite", "source_history_id": opened_version}
        )

        self.document.refresh_from_db()
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.data["code"], "COMPDOC_VERSION_REQUIRED")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "COMPDOC_VERSION_CONFLICT")
        self.assertEqual(self.document.name, "Another editor's update")

    def test_current_version_updates_and_returns_next_audited_version(self):
        """A current write succeeds, records its actor, and advances the version."""

        previous_version = self.current_version()
        response = self.client.patch(
            self.path,
            {"name": "Reviewed update", "source_history_id": previous_version},
        )
        latest_history = self.document.history.first()

        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data["source_history_id"], previous_version)
        self.assertEqual(latest_history.history_user, self.user)

    def current_version(self):
        """Return the version supplied by the authoritative detail response."""

        return self.client.get(self.path).data["source_history_id"]
