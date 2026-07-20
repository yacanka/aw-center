"""Tests for worker-side CompDoc snapshot verification."""

import hashlib

from django.test import SimpleTestCase

from dcc.compdoc_bridge import canonical_json
from dcc.document_job import validate_compliance_bundle
from jobs.contracts import JobExecutionFailure


class CompdocBundleValidationTests(SimpleTestCase):
    """Reject malformed or tampered traceability data before DOCX rendering."""

    def test_valid_bundle_matches_project_and_fingerprint(self):
        """Canonical bridge data passes worker-side defense-in-depth checks."""

        snapshot = snapshot_with([{"id": "one", "name": "Document"}])

        validate_compliance_bundle(snapshot)

    def test_tampered_document_content_is_rejected(self):
        """Content changed after fingerprint creation cannot reach the renderer."""

        snapshot = snapshot_with([{"id": "one", "name": "Document"}])
        snapshot["compliance_documents"]["documents"][0]["name"] = "Tampered"

        with self.assertRaises(JobExecutionFailure) as raised:
            validate_compliance_bundle(snapshot)

        self.assertEqual(raised.exception.code, "DCC_COMPDOC_SNAPSHOT_INVALID")

    def test_cross_project_and_oversized_bundles_are_rejected(self):
        """A worker never renders another project or an unbounded register."""

        cross_project = snapshot_with([])
        cross_project["compliance_documents"]["project_slug"] = "piku"
        oversized = snapshot_with([{"id": str(index)} for index in range(51)])

        for snapshot in (cross_project, oversized):
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(JobExecutionFailure):
                    validate_compliance_bundle(snapshot)


def snapshot_with(documents):
    """Return a DCC snapshot with a correctly calculated register digest."""

    fingerprint = hashlib.sha256(canonical_json(documents)).hexdigest()
    return {
        "project_slug": "ozgur",
        "compliance_documents": {
            "schema_version": 1,
            "project_slug": "ozgur",
            "captured_at": "2026-07-20T00:00:00+00:00",
            "fingerprint": fingerprint,
            "documents": documents,
        },
    }
