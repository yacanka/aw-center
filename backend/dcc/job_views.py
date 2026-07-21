"""HTTP adapters for preview-confirmed durable DCC document jobs."""

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from jira import JIRAError
from jobs.contracts import JobExecutionFailure
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from awcenter.api_errors import error_response
from jobs.api import job_creation_response
from jobs.confirmation import create_confirmation_job
from jobs.models import Job
from jobs.services import (
    IdempotencyConflict, find_idempotent_job, validate_idempotency_key,
)

from .compdoc_bridge import attach_compliance_documents, parse_compdoc_selection
from .compdoc_confirmation import validate_compdoc_preview_current
from .compdoc_recommendations import recommend_compdocs
from .document_preview import prepare_dcc_preview
from .document_snapshot import (
    DccSnapshotError, capture_dcc_snapshot, extract_issue_key, validate_snapshot_size,
)
from .job_error_responses import (
    jira_unavailable_response, snapshot_error_response, unexpected_capture_response,
)
from .job_parameters import build_preview_parameters
from .permissions import DCCAutomationPermission
from .preview_confirmation import confirm_dcc_preview
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
    try:
        compdoc_project, compdoc_ids = parse_compdoc_selection(request.data)
    except DccSnapshotError as error:
        return snapshot_error_response(error)
    return capture_preview_response(request, session_id, issue_reference, compdoc_project, compdoc_ids)


def capture_preview_response(request, session_id, issue_reference, compdoc_project, compdoc_ids):
    """Map JIRA and preview failures to sanitized API errors."""

    try:
        return create_snapshot_preview(
            request, session_id, issue_reference, compdoc_project, compdoc_ids
        )
    except DccSnapshotError as error:
        return snapshot_error_response(error)
    except DccProjectResolutionError:
        return error_response("The JIRA task project is not supported.", code="DCC_PROJECT_INVALID")
    except JIRAError:
        return jira_unavailable_response()
    except IdempotencyConflict:
        raise
    except Exception:
        return unexpected_capture_response(logger)


def create_snapshot_preview(request, session_id, issue_reference, compdoc_project, compdoc_ids):
    """Create or replay one immutable, owner-bound confirmation preview."""

    issue_key = extract_issue_key(issue_reference)
    parameters = build_preview_parameters(issue_key, compdoc_project, compdoc_ids)
    key = validate_idempotency_key(request.headers.get("Idempotency-Key", ""))
    existing = find_idempotent_job(request.user, JOB_KIND, key)
    if existing:
        return replay_snapshot_preview(request.user, existing, parameters)
    snapshot = capture_dcc_snapshot(session_id, issue_key, settings.JIRA_URL)
    attach_compliance_documents(snapshot, request.user, compdoc_project, compdoc_ids)
    recommendations = recommend_compdocs(snapshot, request.user, compdoc_ids)
    validate_snapshot_size(snapshot)
    return persist_snapshot_preview(
        request, issue_key, parameters, snapshot, recommendations, key
    )


def replay_snapshot_preview(user, existing, parameters):
    """Replay only an identical preview that remains authorized."""

    if existing.parameters != parameters:
        raise IdempotencyConflict()
    validate_compdoc_preview_current(user, existing)
    return job_creation_response(existing, False)


def persist_snapshot_preview(request, issue_key, parameters, snapshot, recommendations, key):
    """Persist a dry-rendered private snapshot awaiting explicit confirmation."""

    summary = prepare_dcc_preview(snapshot, recommendations)
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
        try:
            validate_compdoc_preview_current(request.user, job)
            return confirm_dcc_preview(job, request.data)
        except DccSnapshotError as error:
            return snapshot_error_response(error)
        except JobExecutionFailure as error:
            return error_response(str(error), code=error.code, response_status=409)

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
