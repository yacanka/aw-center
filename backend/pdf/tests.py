from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from pypdf import PdfWriter
from rest_framework.test import APIClient


def _pdf_upload(name: str) -> SimpleUploadedFile:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    writer.close()
    return SimpleUploadedFile(name, output.getvalue(), content_type="application/pdf")


class PdfApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = get_user_model().objects.create_user("pdf-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_split_rejects_malformed_parameters_with_stable_error(self):
        response = self.client.post(
            "/api/tools/pdf/split_pdf_zip/",
            {"file": _pdf_upload("input.pdf"), "parameters": "not-json"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "PDF_SPLIT_PARAMETERS_INVALID")

    def test_split_returns_zip_for_valid_parameters(self):
        response = self.client.post(
            "/api/tools/pdf/split_pdf_zip/",
            {
                "file": _pdf_upload("input.pdf"),
                "parameters": '{"parts": 1, "pages_per_parts": null}',
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")

    @patch("pdf.views.comparator.compare", side_effect=RuntimeError("credential-value"))
    def test_compare_does_not_return_exception_detail(self, _compare):
        response = self.client.post(
            "/api/tools/pdf/compare/",
            {
                "first": _pdf_upload("first.pdf"),
                "second": _pdf_upload("second.pdf"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "PDF_COMPARISON_FAILED")
        self.assertNotIn("credential-value", response.content.decode())
