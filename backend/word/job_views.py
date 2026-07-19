import json

from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from awcenter.file_security import WORD_DOCUMENT_POLICY, validate_request_upload
from jobs.api import job_creation_response
from jobs.contracts import JobExecutionFailure
from jobs.services import create_job
from word.analysis import ANALYSIS_CHECKS, validate_check_ids
from word.job_executor import SUPPORTED_TRANSLATIONS


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_translation_job(request):
    """Validate and enqueue a durable Word translation job."""

    uploaded_file = validate_request_upload(request, "file", WORD_DOCUMENT_POLICY)
    translation_type = validate_translation_type(request.data.get("translate_type"))
    job, created = create_job(
        owner=request.user,
        kind="word.translate",
        title=f"Translate {uploaded_file.name}",
        parameters={"translate_type": translation_type},
        uploaded_file=uploaded_file,
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request_id=getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)


def validate_translation_type(value):
    """Validate a translation direction at the API boundary."""

    normalized = str(value or "").lower()
    if normalized not in SUPPORTED_TRANSLATIONS:
        raise ValidationError({"translate_type": "Select a supported translation direction."})
    return normalized


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_analysis_job(request):
    """Validate and enqueue private explainable document analysis."""

    uploaded_file = validate_request_upload(request, "file", WORD_DOCUMENT_POLICY)
    check_ids = parse_check_ids(request.data.get("check_ids"))
    job, created = create_job(
        owner=request.user,
        kind="word.analyze",
        title=f"Analyze {uploaded_file.name}",
        parameters={"check_ids": check_ids},
        uploaded_file=uploaded_file,
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request_id=getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)


def parse_check_ids(value):
    """Parse a JSON checklist and map executor validation to API validation."""

    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        defaults = list(ANALYSIS_CHECKS) if parsed is None else parsed
        return validate_check_ids(defaults)
    except (json.JSONDecodeError, JobExecutionFailure) as error:
        raise ValidationError({"check_ids": "Select only supported analysis checks."}) from error
import json
