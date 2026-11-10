import json
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from pypdf import PdfReader, PdfWriter
from rest_framework.test import APIClient


def _pdf_upload(name: str, pages: int = 1) -> SimpleUploadedFile:
    output = BytesIO()
    writer = PdfWriter()
    for page_number in range(pages):
        writer.add_blank_page(width=72 + page_number, height=72)
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

    def test_split_rejects_more_parts_than_pdf_pages(self):
        response = self.client.post(
            "/api/tools/pdf/split_pdf_zip/",
            {"file": _pdf_upload("input.pdf"), "parameters": '{"parts": 2}'},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "PDF_SPLIT_PARAMETERS_INVALID")

    @patch(
        "pdf.views.PdfReader",
        side_effect=AssertionError("Invalid parts must be rejected first."),
    )
    def test_split_rejects_excessive_parts_before_reading_pdf(self, _reader):
        response = self.client.post(
            "/api/tools/pdf/split_pdf_zip/",
            {"file": _pdf_upload("input.pdf"), "parameters": '{"parts": 100000}'},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "PDF_SPLIT_PARAMETERS_INVALID")

    def test_split_rejects_fractional_parameter_with_stable_error(self):
        response = self.client.post(
            "/api/tools/pdf/split_pdf_zip/",
            {"file": _pdf_upload("input.pdf", pages=3), "parameters": '{"parts": 2.5}'},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "PDF_SPLIT_PARAMETERS_INVALID")

    def test_split_zip_preserves_page_order_in_both_modes(self):
        three_part_names = [
            "part_01_pages_1-2.pdf",
            "part_02_pages_3-4.pdf",
            "part_03_pages_5-5.pdf",
        ]
        cases = (
            ({"parts": 3}, 5, three_part_names),
            ({"pages_per_parts": 2}, 5, three_part_names),
            (
                {"parts": "5"},
                5,
                [f"part_{index:02d}_pages_{index}-{index}.pdf" for index in range(1, 6)],
            ),
            (
                {"pages_per_parts": 3},
                10,
                [
                    "part_01_pages_1-3.pdf",
                    "part_02_pages_4-6.pdf",
                    "part_03_pages_7-8.pdf",
                    "part_04_pages_9-10.pdf",
                ],
            ),
        )
        for parameters, page_count, filenames in cases:
            with self.subTest(parameters=parameters):
                response = self.client.post(
                    "/api/tools/pdf/split_pdf_zip/",
                    {
                        "file": _pdf_upload("input.pdf", pages=page_count),
                        "parameters": json.dumps(parameters),
                    },
                    format="multipart",
                )

                self.assertEqual(response.status_code, 200)
                with ZipFile(BytesIO(response.content)) as archive:
                    self.assertEqual(archive.namelist(), filenames)
                    widths = [
                        int(page.mediabox.width)
                        for name in filenames
                        for page in PdfReader(BytesIO(archive.read(name))).pages
                    ]
                self.assertEqual(widths, list(range(72, 72 + page_count)))

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


class PdfSplitPlanTests(SimpleTestCase):
    def setUp(self):
        from pdf.views import _parse_split_parameters, _split_plan

        self.parse_parameters = _parse_split_parameters
        self.split_plan = _split_plan

    def test_plan_rejects_huge_parts_for_small_pdf(self):
        with self.assertRaises(ValueError):
            self.split_plan(1, 100000, None)

    def test_plan_rejects_explicit_and_derived_parts_above_output_limit(self):
        for parts, pages_per_part in ((1001, None), (None, 1)):
            with self.subTest(parts=parts, pages_per_part=pages_per_part):
                with self.assertRaises(ValueError):
                    self.split_plan(1001, parts, pages_per_part)

    def test_plan_accepts_output_limit_boundary(self):
        self.assertEqual(self.split_plan(1000, 1000, None), [1] * 1000)
        self.assertEqual(self.split_plan(1000, None, 1), [1] * 1000)

    def test_pages_per_part_above_page_count_returns_one_part(self):
        self.assertEqual(self.split_plan(5, None, 10), [5])

    def test_huge_pages_per_part_does_not_overflow_float_conversion(self):
        self.assertEqual(self.split_plan(5, None, 10**400), [5])

    def test_split_parameters_reject_non_integer_numeric_values(self):
        for field in ("parts", "pages_per_parts"):
            for value in (1.0, 1.5, float("inf"), float("nan")):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.parse_parameters(json.dumps({field: value}))

    def test_split_parameters_require_one_positive_integer_option(self):
        cases = (
            {},
            {"parts": 1, "pages_per_parts": 1},
            {"parts": True},
            {"parts": 0},
            {"pages_per_parts": -1},
            {"parts": "1.5"},
            {"parts": []},
            {"parts": {}},
        )
        for parameters in cases:
            with self.subTest(parameters=parameters):
                with self.assertRaises(ValueError):
                    self.parse_parameters(json.dumps(parameters))
