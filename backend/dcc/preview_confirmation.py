"""Confirm a reviewed DCC preview with warning acknowledgement audit."""

from django.utils import timezone
from rest_framework.response import Response

from awcenter.api_errors import error_response
from jobs.models import JobStatus
from jobs.serializers import JobSerializer
from jobs.services import record_event, set_job_state

from .compdoc_traceability import create_traceability_links
from .readiness import validate_readiness_acknowledgement


def confirm_dcc_preview(job, payload):
    """Queue an eligible preview after validating readiness acknowledgement."""

    active = {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED}
    if job.status in active:
        return Response(JobSerializer(job).data)
    if job.status != JobStatus.AWAITING_CONFIRMATION:
        return not_confirmable_response()
    if preview_expired(job):
        job.delete()
        return expired_preview_response()
    warning_codes = validate_readiness_acknowledgement(job.result_summary, payload)
    create_traceability_links(job)
    record_acknowledgement(job, warning_codes)
    set_job_state(job, JobStatus.QUEUED, 0, "Preview confirmed; job queued.")
    return Response(JobSerializer(job).data)


def record_acknowledgement(job, warning_codes):
    """Append a content-free audit event when warnings required review."""

    if not warning_codes:
        return
    record_event(
        job,
        "DCC readiness warnings acknowledged.",
        "DCC_READINESS_ACKNOWLEDGED",
        {"warning_codes": warning_codes},
    )


def preview_expired(job):
    """Return whether an unconfirmed preview passed its bounded lifetime."""

    return not job.confirmation_expires_at or job.confirmation_expires_at <= timezone.now()


def not_confirmable_response():
    """Return the stable response for a terminal non-confirmable preview."""

    return error_response(
        "This DCC preview can no longer be confirmed.",
        code="DCC_PREVIEW_NOT_CONFIRMABLE",
        response_status=409,
    )


def expired_preview_response():
    """Return the stable response for a deleted expired preview."""

    return error_response(
        "The DCC preview expired. Capture the JIRA source again.",
        code="DCC_PREVIEW_EXPIRED",
        response_status=410,
    )
