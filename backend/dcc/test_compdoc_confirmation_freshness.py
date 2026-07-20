"""Regression tests for CompDoc freshness at DCC confirmation time."""

from unittest.mock import patch
from uuid import UUID

from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from projects.ozgur.models import CompDoc

from . import test_compdoc_bridge as bridge_fixtures
from . import test_compdoc_refresh as refresh_fixtures


class CompdocConfirmationFreshnessTests(JobTestCase):
    """Prevent time-of-check/time-of-use drift after preview review."""

    def setUp(self):
        """Create one fully authorized DCC user and source document."""

        super().setUp()
        self.document = CompDoc.objects.create(name="Reviewed Manual", cover_page_no="FRESH-1")
        self.user.user_permissions.add(
            bridge_fixtures.permission("dcc", "add_jira_dcc"),
            bridge_fixtures.permission("ozgur", "view_compdoc"),
        )

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_dcc_visible_change_blocks_confirmation(self, capture, prepare):
        """Confirmation keeps the preview pending when rendered fields advanced."""

        preview = self.create_preview(capture, prepare, "stale-confirmation")
        self.document.name = "Changed after review"
        self.document.save(update_fields=["name"])

        response = self.confirm(preview.data["id"])

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "DCC_COMPDOC_SOURCE_CHANGED")
        self.assertEqual(Job.objects.get(pk=preview.data["id"]).status, JobStatus.AWAITING_CONFIRMATION)

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_non_rendered_change_does_not_block_confirmation(self, capture, prepare):
        """A notes-only history advance does not create a false freshness conflict."""

        preview = self.create_preview(capture, prepare, "notes-confirmation")
        self.document.notes = "Internal metadata"
        self.document.save(update_fields=["notes"])

        response = self.confirm(preview.data["id"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], JobStatus.QUEUED)

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_multiple_documents_use_canonical_snapshot_order(self, capture, prepare):
        """UUID request order cannot create a false multi-document conflict."""

        first = CompDoc.objects.create(id=UUID(int=1), name="Zulu", cover_page_no="MULTI-1")
        second = CompDoc.objects.create(id=UUID(int=2), name="Alpha", cover_page_no="MULTI-2")
        preview = self.create_preview(
            capture, prepare, "multi-confirmation", [str(first.pk), str(second.pk)]
        )

        response = self.confirm(preview.data["id"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], JobStatus.QUEUED)

    def create_preview(self, capture, prepare, key, document_ids=None):
        """Create one real private preview with mocked JIRA rendering only."""

        capture.return_value = bridge_fixtures.snapshot()
        prepare.return_value = bridge_fixtures.preview_summary()
        payload = bridge_fixtures.preview_payload(self.document.pk)
        if document_ids:
            payload["compdoc_ids"] = document_ids
        return self.client.post(
            bridge_fixtures.PREVIEW_URL,
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def confirm(self, job_id):
        """Confirm one owned preview."""

        return self.client.post(f"/dcc/jobs/create-document/{job_id}/confirm/", {}, format="json")


class RefreshedPreviewFreshnessTests(JobTestCase):
    """Verify a stale refresh child can be safely regenerated from its trace."""

    @patch("dcc.compdoc_refresh.prepare_dcc_preview")
    def test_second_refresh_replaces_unconfirmed_stale_child(self, prepare):
        """Semantic replay discards a stale child instead of returning it."""

        prepare.return_value = refresh_fixtures.preview_summary()
        document, trace = self.create_trace()
        document.name = "First refresh"
        document.save(update_fields=["name"])
        first = self.refresh(trace, "first-refresh")
        document.name = "Second refresh"
        document.save(update_fields=["name"])

        blocked = self.client.post(f"/dcc/jobs/create-document/{first.data['id']}/confirm/", {})
        second = self.refresh(trace, "second-refresh")

        self.assertEqual(blocked.data["code"], "DCC_COMPDOC_SOURCE_CHANGED")
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data["id"], second.data["id"])
        self.assertFalse(Job.objects.filter(pk=first.data["id"]).exists())

    def create_trace(self):
        """Create one retained source and authorize its owner."""

        document = CompDoc.objects.create(name="Original", cover_page_no="REFRESH-FRESH")
        self.user.user_permissions.add(
            refresh_fixtures.permission("dcc", "add_jira_dcc"),
            refresh_fixtures.permission("dcc", "view_jira_dcc"),
            refresh_fixtures.permission("ozgur", "view_compdoc"),
        )
        _source, trace = refresh_fixtures.create_source(self.user, document)
        return document, trace

    def refresh(self, trace, key):
        """Create a current-source revision for one trace."""

        return self.client.post(
            f"/dcc/compdoc-traceability/{trace.id}/refresh-preview/",
            {}, format="json", HTTP_IDEMPOTENCY_KEY=key,
        )
