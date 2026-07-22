import json

from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from awcenter.file_security import WORD_DOCUMENT_POLICY, validate_request_upload
from jobs.api import job_creation_response
from jobs.contracts import JobExecutionFailure
from jobs.services import create_job
from word.analysis_contracts import (
    ANALYSIS_CHECKS,
    selected_custom_checks,
    validate_check_ids,
)
from word.custom_checks import get_custom_checks
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
    custom_checks = get_custom_checks(request.user)
    check_ids = parse_check_ids(request.data.get("check_ids"), custom_checks)
    parameters = {"check_ids": check_ids}
    selected_custom = selected_custom_checks(check_ids, custom_checks)
    if selected_custom:
        parameters["custom_checks"] = selected_custom
    job, created = create_job(
        owner=request.user,
        kind="word.analyze",
        title=f"Analyze {uploaded_file.name}",
        parameters=parameters,
        uploaded_file=uploaded_file,
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request_id=getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)


def parse_check_ids(value, custom_checks=None):
    """Parse a JSON checklist and map executor validation to API validation."""

    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        defaults = list(ANALYSIS_CHECKS) if parsed is None else parsed
        return validate_check_ids(defaults, custom_checks)
    except (json.JSONDecodeError, JobExecutionFailure, ValueError) as error:
        raise ValidationError(
            {"check_ids": "Select only default checks or questions saved in your profile."}
        ) from error
import json
