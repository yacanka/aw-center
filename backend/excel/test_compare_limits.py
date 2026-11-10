import json
import re
from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from excel.tests import workbook


class ExcelComparisonLimitsTests(APITestCase):
    def setUp(self):
        self.client.force_authenticate(get_user_model().objects.create_user("excel-limits-user"))
        self.client.raise_request_exception = False

    def compare(self, rows=None, parameters=None, first=None):
        return self.client.post("/api/tools/excel/compare/", {
            "first": first or workbook(rows or [["id", "name"], ["1", "Example"]]),
            "second": workbook([["id", "name"], ["1", "Example"]]),
            "json": json.dumps(parameters or {"keyColumns": ["id"]}),
        }, format="multipart")

    @patch("excel.views.MAX_ROWS", 2, create=True)
    def test_row_budget_rejects_oversized_table(self):
        response = self.compare([["id", "name"], ["1", "One"], ["2", "Two"], ["3", "Three"]])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "EXCEL_COMPARE_LIMIT_EXCEEDED")

    @patch("excel.views.MAX_COLUMNS", 1, create=True)
    def test_column_budget_rejects_wide_table(self):
        response = self.compare()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "EXCEL_COMPARE_LIMIT_EXCEEDED")

    @patch("excel.views.MAX_CHARACTERS", 5, create=True)
    def test_extracted_text_budget_is_enforced(self):
        response = self.compare()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "EXCEL_COMPARE_LIMIT_EXCEEDED")

    def test_duplicate_or_blank_keys_are_invalid_parameters(self):
        for keys in (["id", "id"], [" "], ["id", "   "]):
            with self.subTest(keys=keys):
                response = self.compare(parameters={"keyColumns": keys})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["code"], "EXCEL_COMPARE_INVALID")

    def test_malformed_office_xml_is_input_error(self):
        original = workbook([["id", "name"], ["1", "Example"]])
        output = BytesIO()
        with ZipFile(original) as source, ZipFile(output, "w", ZIP_DEFLATED) as destination:
            for entry in source.infolist():
                destination.writestr(entry, b"<broken" if entry.filename == "xl/worksheets/sheet1.xml" else source.read(entry.filename))
        response = self.compare(first=SimpleUploadedFile("input.xlsx", output.getvalue(), content_type="application/octet-stream"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "EXCEL_COMPARE_INVALID")

    @patch("excel.views.MAX_COLUMNS", 2)
    @patch("pandas.ExcelFile.parse", side_effect=RuntimeError("Full frame allocation reached"))
    def test_forged_dimensions_are_rejected_before_dataframe_allocation(self, _parse):
        original = workbook([["id", "name", "extra"], ["1", "Example", "Content"]])
        output = BytesIO()
        with ZipFile(original) as source, ZipFile(output, "w", ZIP_DEFLATED) as destination:
            for entry in source.infolist():
                content = source.read(entry.filename)
                if entry.filename == "xl/worksheets/sheet1.xml":
                    content = re.sub(br'<dimension ref="[^"]+"', b'<dimension ref="A1:B2"', content)
                destination.writestr(entry, content)
        response = self.compare(first=SimpleUploadedFile("input.xlsx", output.getvalue(), content_type="application/octet-stream"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "EXCEL_COMPARE_LIMIT_EXCEEDED")

    @patch("excel.views.MAX_ROWS", 2)
    def test_row_budget_accepts_table_at_limit(self):
        response = self.compare([["id", "name"], ["1", "One"], ["2", "Two"]])
        self.assertEqual(response.status_code, 200)

    @patch("excel.views.MAX_SYNCHRONOUS_CELLS", 5, create=True)
    @patch("pandas.DataFrame.to_excel", side_effect=RuntimeError("Report allocation reached"))
    def test_combined_cell_budget_is_enforced_before_report_allocation(self, _writer):
        response = self.compare([["id", "name"], ["1", "Old"], ["2", "Old"]])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "EXCEL_COMPARE_LIMIT_EXCEEDED")

    @patch("excel.views.read_excel_first_sheet", side_effect=RuntimeError("private-internal-detail"))
    def test_unexpected_processing_failure_is_safe_500(self, _reader):
        response = self.compare()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["code"], "INTERNAL_ERROR")
        self.assertNotIn("private-internal-detail", str(response.data))
