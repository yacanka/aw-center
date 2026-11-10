import json
import logging
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from django.http import HttpResponse

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from pypdf import PdfReader, PdfWriter

from awcenter.api_errors import error_response
from awcenter.file_security import PDF_POLICY, validate_request_upload
from .comparer.report_generator import HTMLReportGenerator
from .comparer.text_comparator import PDFComparator

logger = logging.getLogger(__name__)
MAX_SPLIT_PARTS = 1000

def _split_plan(num_pages: int, parts: int | None, pages_per_part: int | None):
    if parts is None and pages_per_part is None:
        raise ValueError("Either 'parts' or 'pages_per_part' must be provided.")

    if parts is None:
        if pages_per_part < 1:
            raise ValueError("'pages_per_parts' must be >= 1.")
        parts = (num_pages - 1) // pages_per_part + 1

    if parts < 1:
        raise ValueError("'parts' must be >= 1.")
    if parts > num_pages:
        raise ValueError("'parts' must not exceed the PDF page count.")
    if parts > MAX_SPLIT_PARTS:
        raise ValueError(f"The PDF must produce at most {MAX_SPLIT_PARTS} parts.")

    base, rem = divmod(num_pages, parts)
    return [(base + 1 if i < rem else base) for i in range(parts)]


def _parse_split_parameters(raw_parameters: str | None) -> tuple[int | None, int | None]:
    if raw_parameters is None:
        raise ValueError("Split parameters are required.")
    try:
        parameters = json.loads(raw_parameters)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Split parameters must be valid JSON.") from exc
    if not isinstance(parameters, dict):
        raise ValueError("Split parameters must be an object.")

    parts = _optional_positive_integer(parameters.get("parts"), "parts")
    pages_per_part = _optional_positive_integer(
        parameters.get("pages_per_parts"),
        "pages_per_parts",
    )
    if (parts is None) == (pages_per_part is None):
        raise ValueError("Provide exactly one of 'parts' or 'pages_per_parts'.")
    if parts is not None and parts > MAX_SPLIT_PARTS:
        raise ValueError(f"'parts' must be <= {MAX_SPLIT_PARTS}.")
    return parts, pages_per_part


def _optional_positive_integer(value, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"'{field_name}' must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'{field_name}' must be a positive integer.") from exc
    if parsed < 1:
        raise ValueError(f"'{field_name}' must be a positive integer.")
    return parsed


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def split_pdf_zip(request):
    f = validate_request_upload(request, "file", PDF_POLICY)
    try:
        parts, pages_per_part = _parse_split_parameters(request.POST.get("parameters"))
    except ValueError as exc:
        return error_response(str(exc), "PDF_SPLIT_PARAMETERS_INVALID")

    try:
        reader = PdfReader(f)
    except Exception:
        return error_response("The PDF could not be read.", "PDF_INVALID")

    num_pages = len(reader.pages)
    if num_pages == 0:
        return error_response("The PDF does not contain any pages.", "PDF_EMPTY")

    try:
        plan = _split_plan(num_pages, parts, pages_per_part)
    except ValueError as exc:
        return error_response(str(exc), "PDF_SPLIT_PARAMETERS_INVALID")

    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        start = 0
        for idx, count in enumerate(plan, start=1):
            end = start + count
            writer = PdfWriter()
            for p in range(start, end):
                writer.add_page(reader.pages[p])

            part_buf = BytesIO()
            writer.write(part_buf)
            writer.close()
            part_buf.seek(0)

            zf.writestr(f"part_{idx:02d}_pages_{start+1}-{end}.pdf", part_buf.read())
            start = end

    zip_buffer.seek(0)
    filename = "split_parts.zip"
    resp = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def compare_pdf(request):
    first_pdf = validate_request_upload(request, "first", PDF_POLICY)
    second_pdf = validate_request_upload(request, "second", PDF_POLICY)

    try:
        result = comparator.compare(BytesIO(first_pdf.read()), BytesIO(second_pdf.read()))
        output = BytesIO()
        generator = HTMLReportGenerator()
        generator.save_report(result, output)

        resp = HttpResponse(output.getvalue(), content_type="text/html")
        return resp

    except Exception as exc:
        logger.warning(
            "PDF comparison failed type=%s",
            exc.__class__.__name__,
            extra={"request": request},
        )
        return error_response("PDF comparison failed.", "PDF_COMPARISON_FAILED")


comparator = PDFComparator()
