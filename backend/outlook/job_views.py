"""Durable Outlook job API boundaries."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from awcenter.file_security import MSG_POLICY, validate_request_upload
from jobs.api import job_creation_response
from jobs.services import create_job


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_word_attachment_extraction_job(request):
    """Validate and enqueue one private Outlook attachment extraction job."""

    uploaded_file = validate_request_upload(request, "file", MSG_POLICY)
    job, created = create_job(
        owner=request.user,
        kind="outlook.extract_word_attachment",
        title=f"Extract Word attachment from {uploaded_file.name}"[:160],
        parameters={},
        uploaded_file=uploaded_file,
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request_id=getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)
