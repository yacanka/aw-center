"""Regression tests for both supported ECR PDF table layouts."""

from io import BytesIO

from django.test import SimpleTestCase

from .ecr_parser import EcrPdfParseError, parse_ecr_pdf
from .test_ecr_workflow import ecr_pdf, pdf_document, table_commands


class EcrPdfParserTests(SimpleTestCase):
    def test_current_layout_preserves_review_fields_and_rewinds_upload(self):
        upload = BytesIO(ecr_pdf("Validated change"))
        upload.seek(10)

        snapshot = parse_ecr_pdf(upload)

        self.assertEqual(snapshot["ecr_number"], "ECD-42 / REV")
        self.assertEqual(snapshot["title"], "Validated change")
        self.assertEqual(snapshot["requestor"], "Requestor")
        self.assertEqual(snapshot["originator"], "Originator")
        self.assertEqual(snapshot["ata"], "27")
        self.assertEqual(snapshot["subata"], "10")
        self.assertEqual(snapshot["justification"], "Justification")
        self.assertEqual(snapshot["proposed_solution"], "Solution")
        self.assertEqual(snapshot["nonimplementation_consequence"], "Consequence")
        self.assertEqual(snapshot["impacted_groups"], "Systems")
        self.assertEqual(upload.tell(), 0)

    def test_alternate_layout_is_not_accepted_as_current_layout(self):
        cells = {
            (2, 0): "Alternate change",
            (4, 0): "ECD-42 - Alternate change",
            (4, 1): "AW Center",
            (4, 2): "Minor",
            (4, 3): "Design",
            (7, 0): "Initial",
            (9, 1): "Aircraft 1",
            (10, 1): "Certification",
            (11, 1): "Extra row",
            (12, 1): "Requestor",
            (14, 1): "Originator",
            (15, 1): "27/10",
            (16, 1): "Justification",
            (17, 1): "Solution",
            (18, 1): "Consequence",
            (19, 1): "Systems",
        }
        upload = BytesIO(pdf_document(table_commands(cells, row_count=20)))

        snapshot = parse_ecr_pdf(upload)

        self.assertEqual(snapshot["ecr_number"], "ECD-42")
        self.assertEqual(snapshot["requestor"], "Requestor")
        self.assertEqual(snapshot["originator"], "Originator")
        self.assertEqual(snapshot["ata"], "27")
        self.assertEqual(snapshot["subata"], "10")
        self.assertEqual(snapshot["justification"], "Justification")
        self.assertEqual(snapshot["proposed_solution"], "Solution")
        self.assertEqual(snapshot["nonimplementation_consequence"], "Consequence")
        self.assertEqual(snapshot["impacted_groups"], "Systems")

    def test_unsupported_row_count_cannot_supply_a_false_positive_snapshot(self):
        upload = BytesIO(pdf_document(table_commands({
            (2, 0): "Unrelated table", (4, 0): "A reference",
        }, row_count=21)))

        with self.assertRaises(EcrPdfParseError):
            parse_ecr_pdf(upload)

        self.assertEqual(upload.tell(), 0)
