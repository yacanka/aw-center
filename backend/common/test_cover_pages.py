from django.db import IntegrityError, transaction
from django.test import TestCase

from common.models import CoverPage
from projects.ozgur.models import CompDoc
from projects.ozgur.serializers import CompDocSerializer
from projects.piku.models import CompDoc as PikuCompDoc


class CoverPageRelationshipTests(TestCase):
    """Verify project-scoped one-to-many cover-page relationships."""

    def test_multiple_documents_share_one_cover_page(self):
        """Different compliance documents may belong to the same cover page."""

        first = CompDoc.objects.create(name="Flight Manual", cover_page_no="CP-001")
        second = CompDoc.objects.create(name="Maintenance Manual", cover_page_no="CP-001")

        self.assertEqual(first.cover_page_id, second.cover_page_id)
        self.assertEqual(CoverPage.objects.count(), 1)
        self.assertEqual(first.cover_page.ozgur_compliance_documents.count(), 2)

    def test_cover_page_number_is_scoped_to_project(self):
        """Matching numbers in different projects never share a cover-page record."""

        ozgur = CompDoc.objects.create(name="Ozgur Manual", cover_page_no="CP-001")
        piku = PikuCompDoc.objects.create(name="Piku Manual", cover_page_no="CP-001")

        self.assertNotEqual(ozgur.cover_page_id, piku.cover_page_id)
        self.assertEqual(CoverPage.objects.count(), 2)

    def test_cover_page_issue_is_shared_by_linked_documents(self):
        """Updating the canonical issue keeps compatibility fields synchronized."""

        first = CompDoc.objects.create(
            name="Flight Manual", cover_page_no="CP-001", cover_page_issue="A"
        )
        second = CompDoc.objects.create(
            name="Maintenance Manual", cover_page_no="CP-001", cover_page_issue="B"
        )

        first.refresh_from_db()
        self.assertEqual(first.cover_page_id, second.cover_page_id)
        self.assertEqual(first.cover_page_issue, "B")
        self.assertEqual(first.cover_page.issue, "B")

    def test_duplicate_document_name_on_cover_page_is_rejected(self):
        """The same compliance document cannot be linked twice to one cover page."""

        CompDoc.objects.create(name="Flight Manual", cover_page_no="CP-001")

        with self.assertRaises(IntegrityError), transaction.atomic():
            CompDoc.objects.create(name="Flight Manual", cover_page_no="CP-001")

    def test_serializer_resolves_read_only_cover_page(self):
        """Existing API payloads create the canonical relation without a foreign-key input."""

        serializer = CompDocSerializer(
            data={"name": "Flight Manual", "cover_page_no": "CP-001", "ata": "00-00"}
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        document = serializer.save()
        self.assertEqual(document.cover_page.number, "CP-001")
        self.assertEqual(serializer.data["cover_page"], document.cover_page_id)

    def test_serializer_rejects_duplicate_document_on_cover_page(self):
        """The API returns validation feedback instead of a database integrity error."""

        CompDoc.objects.create(name="Flight Manual", cover_page_no="CP-001")
        serializer = CompDocSerializer(
            data={"name": "Flight Manual", "cover_page_no": "CP-001", "ata": "00-00"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("name", serializer.errors)
