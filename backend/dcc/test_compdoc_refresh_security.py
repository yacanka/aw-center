"""Fail-closed tests for retained DCC snapshot refreshes."""

from unittest.mock import patch

from jobs.tests.base import JobTestCase
from projects.ozgur.models import CompDoc

from . import test_compdoc_refresh as fixtures


class CompdocRefreshSecurityTests(JobTestCase):
    """Verify artifact integrity, lineage, and DCC authorization boundaries."""

    def setUp(self):
        """Create one authorized owner and one retained trace."""

        super().setUp()
        self.document = CompDoc.objects.create(name="Original", cover_page_no="SEC-1")
        self.user.user_permissions.add(
            fixtures.permission("dcc", "add_jira_dcc"),
            fixtures.permission("dcc", "view_jira_dcc"),
            fixtures.permission("ozgur", "view_compdoc"),
        )
        self.source, self.trace = fixtures.create_source(self.user, self.document)
        self.document.name = "Current"
        self.document.save(update_fields=["name"])

    @patch("dcc.compdoc_refresh.prepare_dcc_preview")
    def test_missing_retained_artifact_returns_safe_archive_error(self, prepare):
        """A missing private snapshot never falls back to client or JIRA data."""

        prepare.return_value = fixtures.preview_summary()
        self.source.input_file.storage.delete(self.source.input_file.name)

        response = self.refresh()

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.data["code"], "DCC_COMPDOC_REFRESH_SOURCE_ARCHIVED")

    @patch("dcc.compdoc_refresh.prepare_dcc_preview")
    def test_trace_fingerprint_mismatch_rejects_refresh(self, prepare):
        """A trace cannot be rebound to a different retained snapshot."""

        prepare.return_value = fixtures.preview_summary()
        self.trace.snapshot_fingerprint = "0" * 64
        self.trace.save(update_fields=["snapshot_fingerprint"])

        response = self.refresh()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "DCC_COMPDOC_REFRESH_SOURCE_INVALID")

    def test_missing_dcc_creation_permission_is_forbidden(self):
        """Current project access alone cannot authorize DCC creation."""

        self.user.user_permissions.remove(fixtures.permission("dcc", "add_jira_dcc"))
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_authenticate(self.user)

        response = self.refresh()

        self.assertEqual(response.status_code, 403)

    def refresh(self):
        """Request a refresh with a valid idempotency contract."""

        return self.client.post(
            f"/dcc/compdoc-traceability/{self.trace.id}/refresh-preview/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="security-refresh",
        )
