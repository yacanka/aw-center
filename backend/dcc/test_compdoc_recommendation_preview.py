"""Integrated DCC preview tests for non-binding CompDoc recommendations."""

import json
from unittest.mock import patch

from django.contrib.auth.models import Permission

from jobs.models import Job
from jobs.tests.base import JobTestCase
from projects.ozgur.models import CompDoc

from .test_compdoc_recommendations import create_source_preview, source_snapshot


class CompdocRecommendationPreviewTests(JobTestCase):
    """Verify recommendation metadata enters previews without linking records."""

    def setUp(self):
        super().setUp()
        self.document = CompDoc.objects.create(
            name="Flight Control Manual", cover_page_no="CP-100", tech_doc_no="FM-100",
            panel="Flight Controls", ata="27-00",
        )
        self.dcc_permission = permission("dcc", "add_jira_dcc")
        self.view_permission = permission("ozgur", "view_compdoc")
        self.user.user_permissions.add(self.dcc_permission, self.view_permission)

    @patch(
        "dcc.job_views.prepare_dcc_preview",
        side_effect=lambda _snapshot, recommendations: {
            "type": "dcc_preview", **recommendations,
        },
    )
    @patch("dcc.job_views.capture_dcc_snapshot")
    def test_preview_suggests_but_does_not_implicitly_link(self, capture, _prepare):
        """A strong match remains a human decision outside the immutable input."""

        capture.return_value = source_snapshot("Update FM-100", ["Flight Controls 27-00"])
        response = self.client.post(
            "/dcc/jobs/create-document/preview/",
            {"JSESSIONID": "temporary", "url": "DCC-1"}, format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-recommendations-preview",
        )

        self.assertEqual(response.status_code, 201)
        summary = response.data["result_summary"]
        self.assertTrue(summary["compdoc_recommendations_available"])
        self.assertEqual(summary["compdoc_recommendations"][0]["id"], str(self.document.pk))
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.parameters["compdoc_ids"], [])
        with job.input_file.open("rb") as stored:
            snapshot = json.load(stored)
        self.assertNotIn("compliance_documents", snapshot)

    def test_revision_rejects_oversized_selection_before_snapshot_processing(self):
        """An unbounded recommendation payload cannot trigger private artifact work."""

        source = create_source_preview(self.user)
        response = self.client.post(
            f"/dcc/jobs/create-document/{source.id}/compdoc-recommendations/",
            {"compdoc_ids": [str(self.document.pk)] * 51}, format="json",
            HTTP_IDEMPOTENCY_KEY="dcc-recommendations-limit",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "DCC_COMPDOC_LIMIT")
        self.assertFalse(Job.objects.filter(source_job=source).exists())


def permission(app_label, codename):
    """Resolve one exact Django permission fixture."""

    return Permission.objects.get(content_type__app_label=app_label, codename=codename)
