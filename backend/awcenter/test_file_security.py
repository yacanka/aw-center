"""Regression tests for centralized upload security policies."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from awcenter.file_security import (
    EXCEL_POLICY,
    PDF_POLICY,
    UploadSecurityError,
    validate_uploaded_file,
)


def create_zip_upload(filename: str, entries: dict[str, bytes]) -> SimpleUploadedFile:
    """Create an in-memory ZIP-based upload for policy tests."""

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for entry_name, content in entries.items():
            archive.writestr(entry_name, content)
    return SimpleUploadedFile(filename, output.getvalue(), content_type="application/zip")


class UploadPolicyTests(SimpleTestCase):
    """Verify format, size, archive, and filename enforcement in isolation."""

    def test_valid_ooxml_upload_is_accepted_and_rewound(self):
        """A structurally valid workbook remains readable after validation."""

        upload = create_zip_upload("report.xlsx", {"xl/workbook.xml": b"<workbook/>"})
        upload.seek(3)

        validated = validate_uploaded_file(upload, EXCEL_POLICY)

        self.assertIs(validated, upload)
        self.assertEqual(upload.tell(), 0)

    def test_spoofed_pdf_is_rejected_with_stable_code(self):
        """An extension cannot disguise non-PDF content."""

        upload = SimpleUploadedFile("report.pdf", b"not a pdf", content_type="application/pdf")

        with self.assertRaises(UploadSecurityError) as raised:
            validate_uploaded_file(upload, PDF_POLICY)

        self.assertEqual(raised.exception.get_codes(), "UPLOAD_SIGNATURE_MISMATCH")

    def test_mime_conflict_is_rejected(self):
        """A contradictory declared MIME type is rejected before parsing."""

        upload = SimpleUploadedFile("report.pdf", b"%PDF-1.7", content_type="text/html")

        with self.assertRaises(UploadSecurityError) as raised:
            validate_uploaded_file(upload, PDF_POLICY)

        self.assertEqual(raised.exception.get_codes(), "UPLOAD_MIME_MISMATCH")

    @override_settings(AWCENTER_MAX_DOCUMENT_UPLOAD_BYTES=4)
    def test_environment_size_limit_is_enforced(self):
        """Endpoint limits are environment configurable and fail closed."""

        upload = SimpleUploadedFile("report.pdf", b"%PDF-1.7", content_type="application/pdf")

        with self.assertRaises(UploadSecurityError) as raised:
            validate_uploaded_file(upload, PDF_POLICY)

        self.assertEqual(raised.exception.get_codes(), "UPLOAD_TOO_LARGE")

    @override_settings(AWCENTER_MAX_ARCHIVE_EXPANDED_BYTES=100)
    def test_archive_expansion_limit_blocks_zip_bombs(self):
        """Highly expanding Office packages are rejected without extraction."""

        upload = create_zip_upload("report.xlsx", {"xl/workbook.xml": b"0" * 1000})

        with self.assertRaises(UploadSecurityError) as raised:
            validate_uploaded_file(upload, EXCEL_POLICY)

        self.assertEqual(raised.exception.get_codes(), "UPLOAD_ARCHIVE_LIMIT")

    def test_wrong_ooxml_package_type_is_rejected(self):
        """A Word ZIP renamed as an Excel workbook is rejected."""

        upload = create_zip_upload("report.xlsx", {"word/document.xml": b"<document/>"})

        with self.assertRaises(UploadSecurityError) as raised:
            validate_uploaded_file(upload, EXCEL_POLICY)

        self.assertEqual(raised.exception.get_codes(), "UPLOAD_SIGNATURE_MISMATCH")

    def test_reserved_filename_is_rejected(self):
        """Operating-system device names cannot cross the upload boundary."""

        upload = SimpleUploadedFile("CON.pdf", b"%PDF-1.7", content_type="application/pdf")

        with self.assertRaises(UploadSecurityError) as raised:
            validate_uploaded_file(upload, PDF_POLICY)

        self.assertEqual(raised.exception.get_codes(), "UPLOAD_UNSAFE_NAME")

    def test_archive_path_traversal_entry_is_rejected(self):
        """Archive members cannot escape a future extraction directory."""

        upload = create_zip_upload(
            "report.xlsx",
            {"xl/workbook.xml": b"<workbook/>", "../payload.exe": b"malware"},
        )

        with self.assertRaises(UploadSecurityError) as raised:
            validate_uploaded_file(upload, EXCEL_POLICY)

        self.assertEqual(raised.exception.get_codes(), "UPLOAD_ARCHIVE_UNSAFE")

    def test_empty_upload_is_rejected(self):
        """Empty files fail before MIME or parser inspection."""

        upload = SimpleUploadedFile("report.pdf", b"", content_type="application/pdf")

        with self.assertRaises(UploadSecurityError) as raised:
            validate_uploaded_file(upload, PDF_POLICY)

        self.assertEqual(raised.exception.get_codes(), "UPLOAD_EMPTY")


class UploadEndpointSecurityTests(TestCase):
    """Prove high-risk upload endpoints invoke the shared validator."""

    def setUp(self):
        """Authenticate as an administrator to reach every business parser."""

        self.client = APIClient()
        user = get_user_model().objects.create_superuser("upload-admin", password="pass")
        self.client.force_authenticate(user=user)

    def test_invalid_files_are_rejected_before_domain_parsers(self):
        """Every major document bridge rejects spoofed content consistently."""

        endpoints = [
            ("/pdf/split_pdf_zip/", "payload.pdf", "application/pdf"),
            ("/excel/get_excel_columns/", "payload.xlsx", "application/zip"),
            ("/word/jobs/analyze/", "payload.docx", "application/zip"),
            ("/outlook/msg/parse/", "payload.msg", "application/vnd.ms-outlook"),
            ("/pptxgallery/presentations/upload/", "payload.pptx", "application/zip"),
            ("/ddf/upload/", "payload.docx", "application/zip"),
            ("/dcc/upload/", "payload.pdf", "application/pdf"),
            ("/ozgur/compdocs/upload/", "payload.xlsx", "application/zip"),
            ("/orgs/upload_people/", "payload.xlsx", "application/zip"),
            ("/doors/script/", "payload.xlsx", "application/zip"),
            ("/media-tools/preview/", "payload.mp4", "video/mp4"),
        ]
        for path, filename, content_type in endpoints:
            with self.subTest(path=path):
                upload = SimpleUploadedFile(filename, b"spoofed", content_type=content_type)
                response = self.client.post(path, {"file": upload}, format="multipart")
                self.assertEqual(response.status_code, 400)
                self.assertIn(response.json()["code"], self._content_error_codes())
                self.assertIn("request_id", response.json())

    def test_missing_upload_has_machine_readable_error(self):
        """Missing multipart fields use the same supportable error contract."""

        response = self.client.post("/pdf/split_pdf_zip/", {}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "UPLOAD_REQUIRED")

    @override_settings(AWCENTER_ABSOLUTE_MAX_UPLOAD_BYTES=4)
    def test_streaming_handler_stops_oversized_upload(self):
        """The multipart stream is stopped before an oversized body reaches a parser."""

        upload = SimpleUploadedFile("report.pdf", b"%PDF-1.7", content_type="application/pdf")
        response = self.client.post("/pdf/split_pdf_zip/", {"file": upload}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "UPLOAD_TOO_LARGE")

    @staticmethod
    def _content_error_codes() -> set[str]:
        """Return accepted format rejection codes for flat and archive files."""

        return {"UPLOAD_SIGNATURE_MISMATCH", "UPLOAD_ARCHIVE_INVALID"}
