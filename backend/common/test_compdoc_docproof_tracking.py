"""Persisted DocProof notification-evidence timing tests."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from common.compdoc_docproof import check_docproof
from common.compdoc_tracking_models import CompDocTrackingProfile
from projects.ozgur.models import CompDoc


class CompDocDocProofEvidenceTests(TestCase):
    """Keep revision escalation age stable across periodic refreshes."""

    def setUp(self):
        """Create one document with an already detected newer revision."""

        self.document = CompDoc.objects.create(
            name="Revision Manual",
            cover_page_no="CP-REVISION",
            tech_doc_no="TD-REVISION",
            tech_doc_issue="2",
        )
        self.detected_at = timezone.now() - timedelta(days=2)
        self.profile = CompDocTrackingProfile.objects.create(
            project_slug="ozgur",
            document_id=self.document.pk,
            docproof_issue="3",
            docproof_status="revision_available",
            docproof_issue_detected_at=self.detected_at,
        )

    @patch("common.compdoc_docproof.search_issue_number", return_value=(3, None))
    def test_same_revision_preserves_first_detection_time(self, _search):
        profile = check_docproof(CompDoc, self.document)

        self.assertEqual(profile.docproof_issue_detected_at, self.detected_at)

    @patch("common.compdoc_docproof.search_issue_number", return_value=(4, None))
    def test_new_revision_resets_detection_time(self, _search):
        before = timezone.now()
        profile = check_docproof(CompDoc, self.document)

        self.assertGreaterEqual(profile.docproof_issue_detected_at, before)
