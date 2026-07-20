"""Tests for explainable CompDoc recommendations and immutable preview revisions."""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.utils import timezone

from dcc.compdoc_recommendations import recommend_compdocs
from jobs.confirmation import create_confirmation_job
from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from projects.ozgur.models import CompDoc


class CompdocRecommendationTests(JobTestCase):
    """Verify conservative ranking, permission boundaries, and safe metadata."""

    def setUp(self):
        super().setUp()
        self.exact = create_document(
            "Flight Control Manual", "CP-100", "FM-100", "Flight Controls", "27-00"
        )
        self.ata = create_document(
            "Actuator Instructions", "CP-200", "AI-200", "Hydraulics", "27-00"
        )
        self.unrelated = create_document(
            "Cabin Lighting Manual", "CP-300", "CL-300", "Electrical", "33-00"
        )
        self.view_permission = permission("ozgur", "view_compdoc")

    def test_ranking_is_explainable_bounded_and_permission_protected(self):
        """Explicit references outrank ATA evidence and unauthorized users see no data."""

        snapshot = source_snapshot("Update FM-100 for ATA 27-00", ["Flight Controls review"])
        unavailable = recommend_compdocs(snapshot, self.user)
        self.user.user_permissions.add(self.view_permission)
        self.user = type(self.user).objects.get(pk=self.user.pk)
        available = recommend_compdocs(snapshot, self.user)

        self.assertFalse(unavailable["compdoc_recommendations_available"])
        self.assertEqual(unavailable["compdoc_recommendations"], [])
        self.assertEqual(available["compdoc_recommendations"][0]["id"], str(self.exact.pk))
        self.assertGreaterEqual(available["compdoc_recommendations"][0]["score"], 90)
        self.assertIn(str(self.ata.pk), recommendation_ids(available))
        self.assertNotIn(str(self.unrelated.pk), recommendation_ids(available))
        self.assertNotIn("Update FM-100", str(available))

    def test_selected_documents_are_excluded_from_follow_up_suggestions(self):
        """A preview never recommends a source that is already linked."""

        self.user.user_permissions.add(self.view_permission)
        summary = recommend_compdocs(
            source_snapshot("FM-100 and 27-00"), self.user, [str(self.exact.pk)]
        )

        self.assertNotIn(str(self.exact.pk), recommendation_ids(summary))


class CompdocRecommendationRevisionTests(JobTestCase):
    """Verify derived preview lineage, idempotency, access, and source supersession."""

    def setUp(self):
        super().setUp()
        self.document = create_document(
            "Flight Control Manual", "CP-100", "FM-100", "Flight Controls", "27-00"
        )
        self.dcc_permission = permission("dcc", "add_jira_dcc")
        self.view_permission = permission("ozgur", "view_compdoc")
        self.user.user_permissions.add(self.dcc_permission, self.view_permission)
        self.preview_patch = patch(
            "dcc.compdoc_preview_revision.prepare_dcc_preview",
            side_effect=lambda _snapshot, recommendations: {
                "type": "dcc_preview", **recommendations,
            },
        )
        self.preview_patch.start()
        self.addCleanup(self.preview_patch.stop)
        self.source = create_source_preview(self.user)
        self.url = f"/dcc/jobs/create-document/{self.source.id}/compdoc-recommendations/"

    def test_revision_reuses_verified_jira_snapshot_and_supersedes_source(self):
        """Applying a suggestion creates a linked child without another JIRA credential."""

        response = self.apply("recommendation-revision-1")

        self.assertEqual(response.status_code, 201)
        child = Job.objects.get(pk=response.data["id"])
        self.source.refresh_from_db()
        self.assertEqual(child.source_job, self.source)
        self.assertEqual(child.status, JobStatus.AWAITING_CONFIRMATION)
        self.assertEqual(self.source.status, JobStatus.CANCELLED)
        self.assertFalse(self.source.retryable)
        self.assertEqual(child.parameters["compdoc_ids"], [str(self.document.pk)])
        with child.input_file.open("rb") as stored:
            snapshot = json.load(stored)
        self.assertEqual(snapshot["issue_key"], "DCC-1")
        linked_id = snapshot["compliance_documents"]["documents"][0]["id"]
        self.assertEqual(linked_id, str(self.document.pk))
        source_events = self.source.events.filter(
            code="DCC_COMPDOC_RECOMMENDATIONS_APPLIED"
        )
        self.assertTrue(source_events.exists())
        self.assertTrue(child.events.filter(code="DCC_PREVIEW_DERIVED").exists())

    def test_revision_request_is_idempotent_after_source_supersession(self):
        """A network replay returns the same child even though the source is now cancelled."""

        first = self.apply("recommendation-revision-2")
        second = self.apply("recommendation-revision-2")

        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Job.objects.filter(source_job=self.source).count(), 1)

    def test_revision_requires_owner_permission_and_active_source(self):
        """Ownership, current view access, and preview lifetime are rechecked."""

        self.user.user_permissions.remove(self.view_permission)
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_authenticate(self.user)
        forbidden = self.apply("recommendation-revision-3")
        self.other_user.user_permissions.add(self.dcc_permission)
        self.client.force_authenticate(self.other_user)
        hidden = self.client.post(
            self.url, {"compdoc_ids": [str(self.document.pk)]}, format="json",
            HTTP_IDEMPOTENCY_KEY="recommendation-revision-4",
        )

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.data["code"], "DCC_COMPDOC_FORBIDDEN")
        self.assertEqual(hidden.status_code, 404)

    def test_expired_source_cannot_create_a_fresh_revision(self):
        """A recommendation cannot extend an already expired JIRA review decision."""

        self.source.confirmation_expires_at = timezone.now() - timedelta(seconds=1)
        self.source.save(update_fields=["confirmation_expires_at"])

        response = self.apply("recommendation-revision-5")

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.data["code"], "DCC_PREVIEW_EXPIRED")
        self.assertFalse(Job.objects.filter(source_job=self.source).exists())

    def apply(self, key):
        """Apply the fixture recommendation through the public endpoint."""

        return self.client.post(
            self.url, {"compdoc_ids": [str(self.document.pk)]}, format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )


def create_source_preview(user):
    """Persist an isolated DCC preview fixture with a valid private snapshot."""

    snapshot = source_snapshot("Update FM-100", ["Flight Controls 27-00"])
    upload = ContentFile(json.dumps(snapshot).encode(), name="dcc-DCC-1.json")
    job, _created = create_confirmation_job(
        user, "dcc.create_document", "Create DCC for DCC-1",
        {"issue_key": "DCC-1", "compdoc_project": "", "compdoc_ids": []},
        upload, timezone.now() + timedelta(minutes=15), {"type": "dcc_preview"},
    )
    return job


def create_document(name, cover, technical, panel, ata):
    """Create one common CompDoc recommendation fixture."""

    return CompDoc.objects.create(
        name=name, cover_page_no=cover, tech_doc_no=technical,
        panel=panel, ata=ata, status_flow=[{"status": "authority_approved"}],
    )


def source_snapshot(title, panel_titles=None):
    """Return a valid immutable Ozgur DCC snapshot fixture."""

    return {
        "schema_version": 1, "issue_key": "DCC-1", "project_slug": "ozgur",
        "project_label": "Ozgur", "output_name": "DCC-1.docx", "panel_count": 1,
        "panel_titles": panel_titles or [], "placeholders": {"Design_Change_Title": title},
    }


def recommendation_ids(summary):
    """Return recommendation identifiers from a safe summary."""

    return [item["id"] for item in summary["compdoc_recommendations"]]


def permission(app_label, codename):
    """Resolve one exact Django permission fixture."""

    return Permission.objects.get(content_type__app_label=app_label, codename=codename)
