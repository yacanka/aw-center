"""HTTP adapters for preview-confirmed durable DCC document jobs."""

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from jira import JIRAError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import error_response
from jobs.api import job_creation_response
from jobs.confirmation import create_confirmation_job
from jobs.models import Job, JobStatus
from jobs.serializers import JobSerializer
from jobs.services import (
    IdempotencyConflict, find_idempotent_job, set_job_state, validate_idempotency_key,
)

from .document_preview import prepare_dcc_preview
from .document_snapshot import DccSnapshotError, capture_dcc_snapshot, extract_issue_key
from .permissions import DCCAutomationPermission
from .services.project_resolver import DccProjectResolutionError

logger = logging.getLogger(__name__)
JOB_KIND = "dcc.create_document"


@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCAutomationPermission])
def preview_dcc_document_job(request):
    """Capture and dry-render a private snapshot without exposing it to workers."""

    session_id = str(request.data.get("JSESSIONID") or "").strip()
    issue_reference = str(request.data.get("url") or "").strip()
    validation_response = validate_request_values(session_id, issue_reference)
    if validation_response:
        return validation_response
    return capture_preview_response(request, session_id, issue_reference)


def capture_preview_response(request, session_id, issue_reference):
    """Map JIRA and preview failures to sanitized API errors."""

    try:
        return create_snapshot_preview(request, session_id, issue_reference)
    except DccSnapshotError as error:
        return error_response(str(error), code=error.code)
    except DccProjectResolutionError:
        return error_response("The JIRA task project is not supported.", code="DCC_PROJECT_INVALID")
    except JIRAError:
        return error_response(
            "JIRA could not authenticate or read the task.", code="DCC_JIRA_UNAVAILABLE",
            response_status=502,
        )
    except IdempotencyConflict:
        raise
    except Exception:
        logger.exception("DCC preview capture failed")
        return error_response(
            "The DCC source could not be previewed.", code="DCC_CAPTURE_FAILED",
            response_status=502,
        )


def create_snapshot_preview(request, session_id, issue_reference):
    """Create or replay one immutable, owner-bound confirmation preview."""

    issue_key = extract_issue_key(issue_reference)
    parameters = {"issue_key": issue_key, "snapshot_schema": 1, "confirmation_required": True}
    key = validate_idempotency_key(request.headers.get("Idempotency-Key", ""))
    existing = find_idempotent_job(request.user, JOB_KIND, key)
    if existing:
        if existing.parameters != parameters:
            raise IdempotencyConflict()
        return job_creation_response(existing, False)
    snapshot = capture_dcc_snapshot(session_id, issue_key, settings.JIRA_BTB_URL)
    summary = prepare_dcc_preview(snapshot)
    expires_at = timezone.now() + timedelta(seconds=preview_ttl_seconds())
    job, created = create_confirmation_job(
        request.user, JOB_KIND, f"Create DCC for {issue_key}", parameters,
        snapshot_upload(snapshot, issue_key), expires_at, summary, key,
        getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)


@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCAutomationPermission])
def confirm_dcc_document_job(request, job_id):
    """Queue the exact owned snapshot after an explicit, time-bounded confirmation."""

    with transaction.atomic():
        job = Job.objects.select_for_update().filter(
            pk=job_id, owner=request.user, kind=JOB_KIND,
        ).first()
        if job is None:
            return error_response("DCC preview was not found.", code="DCC_PREVIEW_NOT_FOUND", response_status=404)
        return confirm_locked_preview(job)


def confirm_locked_preview(job):
    """Perform one idempotent state transition while the preview row is locked."""

    active = {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED}
    if job.status in active:
        return Response(JobSerializer(job).data)
    if job.status != JobStatus.AWAITING_CONFIRMATION:
        return error_response(
            "This DCC preview can no longer be confirmed.",
            code="DCC_PREVIEW_NOT_CONFIRMABLE", response_status=409,
        )
    if not job.confirmation_expires_at or job.confirmation_expires_at <= timezone.now():
        job.delete()
        return error_response(
            "The DCC preview expired. Capture the JIRA source again.",
            code="DCC_PREVIEW_EXPIRED", response_status=410,
        )
    set_job_state(job, JobStatus.QUEUED, 0, "Preview confirmed; job queued.")
    return Response(JobSerializer(job).data)


def snapshot_upload(snapshot, issue_key):
    """Create the private generated JSON input consumed by the worker."""

    content = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return ContentFile(content, name=f"dcc-{issue_key}.json")


def preview_ttl_seconds():
    """Return a bounded confirmation lifetime from deployment configuration."""

    return max(60, min(int(settings.DCC_PREVIEW_TTL_SECONDS), 86400))


def validate_request_values(session_id, issue_reference):
    """Reject missing or implausibly large transient request values."""

    if not session_id or not issue_reference:
        return error_response("JIRA session and task URL are required.", code="DCC_FIELDS_REQUIRED")
    if len(session_id) > 4096 or len(issue_reference) > 2048:
        return error_response("JIRA session or task URL is too long.", code="DCC_FIELDS_INVALID")
    return None
