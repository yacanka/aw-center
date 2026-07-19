"""Central upload validation policies for AW Center file-processing endpoints."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from rest_framework.exceptions import APIException

from awcenter.media_signatures import MEDIA_EXTENSIONS, matches_media_signature

MEBIBYTE = 1024 * 1024
SAFE_NAME_PATTERN = re.compile(r"^[^\x00-\x1f<>:\"/\\|?*]+$")
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
OOXML_MARKERS = {
    ".docx": "word/document.xml",
    ".docm": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".xlsm": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}
OLE_EXTENSIONS = {".xls", ".msg"}
ZIP_EXTENSIONS = set(OOXML_MARKERS) | {".zip"}
MAGIC_BYTES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
    ".gif": (b"GIF87a", b"GIF89a"),
}
MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".docm": {"application/vnd.ms-word.document.macroenabled.12"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".xlsm": {"application/vnd.ms-excel.sheet.macroenabled.12"},
    ".xls": {"application/vnd.ms-excel", "application/x-ole-storage"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".msg": {"application/vnd.ms-outlook", "application/x-ole-storage"},
}


class UploadSecurityError(APIException):
    """Represent a rejected upload through the standard API error contract."""

    status_code = 400
    default_code = "UPLOAD_INVALID"
    default_detail = "The uploaded file is invalid."


@dataclass(frozen=True)
class UploadPolicy:
    """Describe extensions and limits accepted by an upload endpoint."""

    extensions: frozenset[str]
    limit_setting: str = "AWCENTER_MAX_DOCUMENT_UPLOAD_BYTES"
    default_limit: int = 50 * MEBIBYTE

    @property
    def maximum_bytes(self) -> int:
        """Return the active environment-backed upload size limit."""

        return int(getattr(settings, self.limit_setting, self.default_limit))


PDF_POLICY = UploadPolicy(frozenset({".pdf"}))
WORD_POLICY = UploadPolicy(frozenset({".docx", ".docm"}))
WORD_DOCUMENT_POLICY = UploadPolicy(frozenset({".docx"}))
EXCEL_POLICY = UploadPolicy(frozenset({".xlsx", ".xlsm", ".xls"}))
OOXML_WORKBOOK_POLICY = UploadPolicy(frozenset({".xlsx", ".xlsm"}))
PRESENTATION_POLICY = UploadPolicy(frozenset({".pptx"}))
MSG_POLICY = UploadPolicy(frozenset({".msg"}))
IMAGE_POLICY = UploadPolicy(
    frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"}),
    "AWCENTER_MAX_IMAGE_UPLOAD_BYTES",
    10 * MEBIBYTE,
)
MEDIA_POLICY = UploadPolicy(
    frozenset(set(IMAGE_POLICY.extensions) | set(MEDIA_EXTENSIONS)),
    "AWCENTER_MAX_MEDIA_UPLOAD_BYTES",
    500 * MEBIBYTE,
)
ATTACHMENT_POLICY = UploadPolicy(
    frozenset(set(MAGIC_BYTES) | ZIP_EXTENSIONS | OLE_EXTENSIONS | {".txt", ".csv"}),
    "AWCENTER_MAX_ATTACHMENT_UPLOAD_BYTES",
    100 * MEBIBYTE,
)


def validate_request_upload(request, field_name: str, policy: UploadPolicy):
    """Return a validated request file or raise a machine-readable API error."""

    uploaded_file = request.FILES.get(field_name)
    if uploaded_file is None:
        if getattr(request, "upload_limit_exceeded", False):
            _reject("The upload exceeds the absolute server limit.", "UPLOAD_TOO_LARGE")
        _reject(f"Upload field '{field_name}' is required.", "UPLOAD_REQUIRED")
    return validate_uploaded_file(uploaded_file, policy)


def validate_uploaded_file(uploaded_file, policy: UploadPolicy):
    """Validate name, size, declared type, signature, and archive safety."""

    extension = _validate_name(uploaded_file.name, policy)
    _validate_size(uploaded_file.size, policy)
    _validate_declared_type(uploaded_file, extension)
    try:
        _validate_content(uploaded_file, extension)
    finally:
        uploaded_file.seek(0)
    return uploaded_file


def _validate_name(name: str, policy: UploadPolicy) -> str:
    normalized_name = str(name or "").strip()
    if not normalized_name or len(normalized_name) > 180 or not SAFE_NAME_PATTERN.fullmatch(normalized_name):
        _reject("The uploaded filename is unsafe.", "UPLOAD_UNSAFE_NAME")
    extension = Path(normalized_name).suffix.lower()
    if extension not in policy.extensions:
        supported = ", ".join(sorted(policy.extensions))
        _reject(f"Unsupported file type. Allowed extensions: {supported}.", "UPLOAD_TYPE_UNSUPPORTED")
    if Path(normalized_name).stem.upper() in WINDOWS_RESERVED_NAMES:
        _reject("The uploaded filename is reserved by the operating system.", "UPLOAD_UNSAFE_NAME")
    return extension


def _validate_size(size: int, policy: UploadPolicy) -> None:
    if not size:
        _reject("The uploaded file is empty.", "UPLOAD_EMPTY")
    if int(size) > policy.maximum_bytes:
        maximum_mebibytes = policy.maximum_bytes // MEBIBYTE
        _reject(f"The uploaded file exceeds the {maximum_mebibytes} MB limit.", "UPLOAD_TOO_LARGE")


def _validate_declared_type(uploaded_file, extension: str) -> None:
    declared_type = str(getattr(uploaded_file, "content_type", "") or "").split(";", 1)[0].lower()
    if not declared_type or declared_type == "application/octet-stream":
        return
    allowed_types = MIME_TYPES.get(extension)
    archive_types = {"application/zip", "application/x-zip-compressed"}
    if allowed_types and declared_type not in allowed_types and declared_type not in archive_types:
        _reject("The declared MIME type conflicts with the file extension.", "UPLOAD_MIME_MISMATCH")


def _validate_content(uploaded_file, extension: str) -> None:
    uploaded_file.seek(0)
    header = uploaded_file.read(16)
    if extension in ZIP_EXTENSIONS:
        _validate_archive(uploaded_file, extension)
    elif extension in OLE_EXTENSIONS and not header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        _reject("The file content does not match its legacy Office type.", "UPLOAD_SIGNATURE_MISMATCH")
    elif extension in MAGIC_BYTES and not any(header.startswith(magic) for magic in MAGIC_BYTES[extension]):
        _reject("The file content does not match its extension.", "UPLOAD_SIGNATURE_MISMATCH")
    elif extension in {".txt", ".csv"} and b"\x00" in header:
        _reject("Text uploads cannot contain binary null bytes.", "UPLOAD_SIGNATURE_MISMATCH")
    elif extension in MEDIA_EXTENSIONS and not matches_media_signature(extension, header):
        _reject("The file content does not match its media container.", "UPLOAD_SIGNATURE_MISMATCH")
    if extension == ".webp" and header[8:12] != b"WEBP":
        _reject("The file content does not match WebP format.", "UPLOAD_SIGNATURE_MISMATCH")


def _validate_archive(uploaded_file, extension: str) -> None:
    uploaded_file.seek(0)
    try:
        with ZipFile(uploaded_file) as archive:
            entries = archive.infolist()
            _validate_archive_entries(entries)
            marker = OOXML_MARKERS.get(extension)
            if marker and marker not in {entry.filename for entry in entries}:
                _reject("The Office package does not match its extension.", "UPLOAD_SIGNATURE_MISMATCH")
    except BadZipFile as error:
        raise UploadSecurityError("The uploaded archive is corrupted.", code="UPLOAD_ARCHIVE_INVALID") from error


def _validate_archive_entries(entries) -> None:
    if len(entries) > int(getattr(settings, "AWCENTER_MAX_ARCHIVE_ENTRIES", 5000)):
        _reject("The uploaded archive contains too many entries.", "UPLOAD_ARCHIVE_LIMIT")
    expanded_limit = int(getattr(settings, "AWCENTER_MAX_ARCHIVE_EXPANDED_BYTES", 250 * MEBIBYTE))
    if sum(entry.file_size for entry in entries) > expanded_limit:
        _reject("The uploaded archive expands beyond the safety limit.", "UPLOAD_ARCHIVE_LIMIT")
    for entry in entries:
        path = PurePosixPath(entry.filename)
        if path.is_absolute() or ".." in path.parts or entry.flag_bits & 0x1:
            _reject("The uploaded archive contains an unsafe entry.", "UPLOAD_ARCHIVE_UNSAFE")
        if entry.compress_size and entry.file_size > entry.compress_size * 250:
            _reject("The uploaded archive has an unsafe compression ratio.", "UPLOAD_ARCHIVE_LIMIT")


def _reject(detail: str, code: str) -> None:
    raise UploadSecurityError(detail, code=code)
