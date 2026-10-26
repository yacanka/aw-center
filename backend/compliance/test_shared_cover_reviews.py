"""Shared cover evidence participates in every affected document's version."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from types import SimpleNamespace

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient

from orgs.models import Project
from .models import ComplianceDocument, CoverPage, ReviewTask
from .serializers import ComplianceDocumentSerializer
from .services import update_document


class SharedCoverReviewTests(TestCase):
    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.user = get_user_model().objects.create_superuser("a10001")
        self.cover = CoverPage.objects.create(project=self.project, number="CP-SHARED", issue="A")
        self.documents = [ComplianceDocument.objects.create(
            project=self.project, cover_page=self.cover, name=name,
        ) for name in ("First document", "Second document")]
        self.reviews = [ReviewTask.objects.create(
            document=document, kind=ReviewTask.Kind.APPROVAL, assignee=self.user,
            assignee_username=self.user.username, requested_by=self.user,
            requested_by_username=self.user.username, request_note="Review revision A.",
            source_version=1,
        ) for document in self.documents]
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = "/api/projects/ozgur/compliance-documents/"

    def test_shared_revision_invalidates_other_document_review_and_records_history(self):
        changed = self.client.patch(self.base + f"{self.documents[0].pk}/", {
            "version": 1, "cover_page": {"number": "CP-SHARED", "issue": "B", "version": 1},
        }, format="json")
        self.assertEqual(changed.status_code, 200)
        decision = self.client.post(
            self.base + f"{self.documents[1].pk}/reviews/{self.reviews[1].pk}/decision/",
            {"status": "approved", "decision_note": "Approving revision A."}, format="json",
        )
        self.assertEqual(decision.status_code, 400)
        for document, review in zip(self.documents, self.reviews):
            document.refresh_from_db()
            review.refresh_from_db()
            self.assertEqual(document.version, 2)
            self.assertEqual(document.cover_page.issue, "B")
            self.assertEqual(review.status, ReviewTask.Status.SUPERSEDED)
            self.assertEqual(document.history.first().version, 2)
            self.assertEqual(document.history.first().history_user_id, self.user.pk)

    def test_creating_a_document_with_revised_shared_cover_invalidates_existing_reviews(self):
        response = self.client.post(self.base, {
            "name": "Third document",
            "cover_page": {"number": "CP-SHARED", "issue": "B", "version": 1},
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["version"], 1)
        for document, review in zip(self.documents, self.reviews):
            document.refresh_from_db()
            review.refresh_from_db()
            self.assertEqual(document.version, 2)
            self.assertEqual(review.status, ReviewTask.Status.SUPERSEDED)

    def test_unchanged_shared_issue_preserves_other_document_review(self):
        response = self.client.patch(self.base + f"{self.documents[0].pk}/", {
            "version": 1, "notes": "First document only",
            "cover_page": {"number": "CP-SHARED", "issue": "A", "version": 1},
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.documents[1].refresh_from_db()
        self.reviews[1].refresh_from_db()
        self.assertEqual(self.documents[1].version, 1)
        self.assertEqual(self.reviews[1].status, ReviewTask.Status.PENDING)

    def test_import_can_update_both_documents_when_the_first_row_revises_their_cover(self):
        output = BytesIO()
        pd.DataFrame([{
            "Document Name": document.name, "Cover Page Number": "CP-SHARED",
            "Cover Page Issue": "B", "Notes": "Imported changes",
        } for document in self.documents]).to_excel(output, index=False)
        def upload():
            return SimpleUploadedFile("shared.xlsx", output.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        preview = self.client.post(self.base + "imports/preview/", {"file": upload()}, format="multipart")
        self.assertEqual(preview.status_code, 200)
        confirmed = self.client.post(self.base + "imports/confirm/", {
            "file": upload(), "confirmation_token": preview.data["confirmation_token"],
        }, format="multipart")
        self.assertEqual(confirmed.status_code, 201, confirmed.data)
        for document, review in zip(self.documents, self.reviews):
            document.refresh_from_db()
            review.refresh_from_db()
            self.assertEqual(document.cover_page.issue, "B")
            self.assertEqual(document.notes, "Imported changes")
            self.assertEqual(review.status, ReviewTask.Status.SUPERSEDED)


@override_settings(DEBUG=False)
class SharedCoverConcurrencyTests(TransactionTestCase):
    def test_updates_of_different_documents_sharing_a_cover_have_one_winner(self):
        project, _ = Project.objects.get_or_create(slug="ozgur", defaults={"name": "Ozgur"})
        user = get_user_model().objects.create_superuser("a10001")
        cover = CoverPage.objects.create(project=project, number="CP-RACE", issue="A")
        documents = [ComplianceDocument.objects.create(
            project=project, cover_page=cover, name=name,
        ) for name in ("First document", "Second document")]
        start = Barrier(2)
        def update(proposal):
            document, issue = proposal
            try:
                serializer = ComplianceDocumentSerializer(document, data={
                    "cover_page": {"number": "CP-RACE", "issue": issue, "version": 1},
                }, partial=True, context={"project": project, "request": SimpleNamespace(user=user)})
                serializer.is_valid(raise_exception=True)
                start.wait(timeout=10)
                update_document(project=project, document_id=document.pk, expected_version=1,
                                serializer=serializer, user=user)
                return 200
            except APIException as error:
                return error.status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(update, zip(documents, ("B", "C")), timeout=30))
        self.assertCountEqual(outcomes, [200, 409])
        self.assertEqual(list(ComplianceDocument.objects.order_by("name").values_list("version", flat=True)), [2, 2])
