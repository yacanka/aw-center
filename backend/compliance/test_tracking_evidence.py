"""Document edits must not reuse DocProof evidence for another identity/revision."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient

from orgs.models import Project
from .models import ComplianceDocument, CoverPage, TrackingProfile
from .notifications import detect_events
from .serializers import ComplianceDocumentSerializer


class TrackingEvidenceMutationTests(TestCase):
    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.user = get_user_model().objects.create_superuser("a10001")
        cover = CoverPage.objects.create(project=self.project, number="CP-EVIDENCE")
        self.document = ComplianceDocument.objects.create(
            project=self.project, cover_page=cover, name="Evidence document",
            number="TD-ONE", issue="A",
        )
        self.checked_at = timezone.now()
        self.profile = TrackingProfile.objects.create(
            document=self.document, docproof_issue="B", docproof_status="revision_available",
            docproof_checked_at=self.checked_at, notification_events=["revision_available"],
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = "/api/projects/ozgur/compliance-documents/"
        self.url = f"{self.base}{self.document.pk}/"

    def patch_document(self, **values):
        response = self.client.patch(self.url, {"version": 1, **values}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.document.refresh_from_db()
        self.profile.document = self.document

    def test_matching_revision_recomputes_evidence_and_fences_stale_tracking_save(self):
        self.patch_document(issue="B")
        self.assertEqual(self.profile.docproof_status, "current")
        self.assertEqual(self.profile.docproof_checked_at, self.checked_at)
        self.assertEqual(self.profile.version, 2)
        self.assertEqual(self.profile.updated_by, self.user)
        self.assertEqual(detect_events(self.profile), {})
        stale = self.client.put(self.url + "tracking/", {
            "version": 1, "notification_enabled": False,
        }, format="json")
        self.assertEqual(stale.status_code, 409)

    def test_changed_identity_discards_remote_evidence_and_preserves_preferences(self):
        self.patch_document(number="TD-TWO")
        self.assertEqual(self.profile.docproof_status, "never_checked")
        self.assertEqual(self.profile.docproof_issue, "")
        self.assertIsNone(self.profile.docproof_checked_at)
        self.assertEqual(self.profile.notification_events, ["revision_available"])
        self.assertEqual(self.profile.version, 2)
        self.assertEqual(detect_events(self.profile), {})

    def test_revision_difference_recomputes_previously_current_evidence(self):
        self.profile.docproof_status = "current"
        self.profile.docproof_issue = "A"
        self.profile.save()
        self.patch_document(issue="B")
        self.assertEqual(self.profile.docproof_status, "revision_available")
        self.assertEqual(self.profile.version, 2)

    def test_unrelated_edit_does_not_invalidate_evidence_or_tracking_version(self):
        self.patch_document(notes="Notes only")
        self.assertEqual(self.profile.docproof_status, "revision_available")
        self.assertEqual(self.profile.version, 1)
        self.assertEqual(self.profile.docproof_checked_at, self.checked_at)

    def test_failed_lookup_is_not_reinterpreted_as_success_after_revision_edit(self):
        self.profile.docproof_status = "not_found"
        self.profile.docproof_issue = ""
        self.profile.save()
        self.patch_document(issue="B")
        self.assertEqual(self.profile.docproof_status, "not_found")
        self.assertEqual(self.profile.version, 2)

    def test_issue_edit_fences_a_lookup_started_without_cached_evidence(self):
        self.profile.docproof_status = "never_checked"
        self.profile.docproof_issue = ""
        self.profile.docproof_checked_at = None
        self.profile.save()

        def document_changes_during_lookup(_number):
            self.patch_document(issue="B")
            return "A", None

        with patch("compliance.services.search_document_issue", side_effect=document_changes_during_lookup):
            result = self.client.post(self.url + "tracking/docproof/", {"version": 1}, format="json")
        self.assertEqual(result.status_code, 409)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.docproof_status, "never_checked")
        self.assertEqual(self.profile.docproof_issue, "")
        self.assertEqual(self.profile.version, 2)

    def test_imported_revision_recomputes_tracking_evidence(self):
        workbook = Workbook()
        workbook.active.append(["Document Name", "Cover Page Number", "Technical Document No", "Technical Document Issue"])
        workbook.active.append([self.document.name, "CP-EVIDENCE", "TD-ONE", "B"])
        content = BytesIO()
        workbook.save(content)

        def upload():
            return SimpleUploadedFile("evidence.xlsx", content.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        preview = self.client.post(self.base + "imports/preview/", {"file": upload()}, format="multipart")
        self.assertEqual(preview.status_code, 200, preview.data)
        confirmed = self.client.post(self.base + "imports/confirm/", {
            "file": upload(), "confirmation_token": preview.data["confirmation_token"],
        }, format="multipart")
        self.assertEqual(confirmed.status_code, 201, confirmed.data)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.docproof_status, "current")
        self.assertEqual(self.profile.version, 2)

    def test_serializer_write_used_by_number_allocation_updates_evidence(self):
        serializer = ComplianceDocumentSerializer(self.document, data={"number": "TD-TWO"},
            partial=True, context={"project": self.project, "request": SimpleNamespace(user=self.user)})
        serializer.is_valid(raise_exception=True)
        serializer.save(version=2)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.docproof_status, "never_checked")
        self.assertEqual(self.profile.version, 2)
