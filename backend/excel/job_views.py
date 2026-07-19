from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from awcenter.file_security import OOXML_WORKBOOK_POLICY, validate_request_upload
from jobs.api import job_creation_response
from jobs.services import create_job
from .cover_pages import inspect_workbook_columns


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_cover_page_job(request):
    """Validate and enqueue durable cover-page generation."""

    uploaded_file = validate_request_upload(request, "file", OOXML_WORKBOOK_POLICY)
    _columns, missing = inspect_workbook_columns(uploaded_file)
    if missing:
        raise ValidationError({"file": f"Missing required columns: {', '.join(missing)}"})
    job, created = create_job(
        owner=request.user,
        kind="excel.cover_pages",
        title=f"Create cover pages from {uploaded_file.name}",
        parameters={},
        uploaded_file=uploaded_file,
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request_id=getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)
