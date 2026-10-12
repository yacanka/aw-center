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
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated

from awcenter.api_errors import error_response
from integrations.jira.sessions import (
    JiraSessionError,
    has_legacy_jira_credential,
    jira_connector_for,
)
from jobs.api import job_creation_response
from jobs.confirmation import create_confirmation_job
from jobs.models import Job
from jobs.services import IdempotencyConflict, find_idempotent_job, require_idempotency_key

from .document_preview import prepare_dcc_preview
from .document_snapshot import (
    DccSnapshotError, capture_dcc_snapshot, extract_issue_key, validate_snapshot_size,
)
from .job_error_responses import (
    jira_unavailable_response, snapshot_error_response, unexpected_capture_response,
)
from .job_parameters import build_preview_parameters
from .access_policy import OPERATOR, require_projects_role
from .access_policy import enabled_projects_by_ids
from .preview_confirmation import confirm_dcc_preview
from .services.project_resolver import DccProjectResolutionError

logger = logging.getLogger(__name__)
JOB_KIND = "dcc.create_document"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def preview_dcc_document_job(request):
    """Capture and dry-render a private snapshot without exposing it to workers."""

    legacy_error = reject_legacy_session_input(request)
    if legacy_error:
        return legacy_error
    issue_reference = str(request.data.get("url") or "").strip()
    validation_response = validate_request_values(issue_reference)
    if validation_response:
        return validation_response
    try:
        connector = jira_connector_for(request.user)
    except JiraSessionError as error:
        return error_response(
            error.detail,
            code=error.code,
            response_status=error.response_status,
        )
    return capture_preview_response(request, connector, issue_reference)


def capture_preview_response(request, connector, issue_reference):
    """Map JIRA and preview failures to sanitized API errors."""

    try:
        return create_snapshot_preview(request, connector, issue_reference)
    except DccSnapshotError as error:
        return snapshot_error_response(error)
    except DccProjectResolutionError:
        return error_response("The JIRA task project is not supported.", code="DCC_PROJECT_INVALID")
    except JIRAError:
        return jira_unavailable_response()
    except IdempotencyConflict:
        raise
    except APIException:
        raise
    except Exception:
        return unexpected_capture_response(logger)


def create_snapshot_preview(request, connector, issue_reference):
    """Create or replay one immutable, owner-bound confirmation preview."""

    issue_key = extract_issue_key(issue_reference)
    key = require_idempotency_key(request.headers.get("Idempotency-Key", ""))
    existing = find_idempotent_job(request.user, JOB_KIND, key)
    if existing:
        return replay_snapshot_preview(request.user, existing, issue_key)
    snapshot = capture_dcc_snapshot(connector, issue_key, request.user)
    validate_snapshot_size(snapshot)
    parameters = build_preview_parameters(issue_key, snapshot["project_ids"])
    return persist_snapshot_preview(request, issue_key, parameters, snapshot, key)


def replay_snapshot_preview(actor, existing, issue_key):
    """Replay only an identical preview that remains authorized."""

    if existing.parameters.get("issue_key") != issue_key:
        raise IdempotencyConflict()
    projects = enabled_projects_by_ids(existing.parameters.get("project_ids", ()))
    require_projects_role(actor, projects, OPERATOR)
    return job_creation_response(existing, False)


def persist_snapshot_preview(request, issue_key, parameters, snapshot, key):
    """Persist a dry-rendered private snapshot awaiting explicit confirmation."""

    summary = prepare_dcc_preview(snapshot)
    expires_at = timezone.now() + timedelta(seconds=preview_ttl_seconds())
    job, created = create_confirmation_job(
        request.user, JOB_KIND, f"Create DCC for {issue_key}", parameters,
        snapshot_upload(snapshot, issue_key), expires_at, summary, key,
        getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_dcc_document_job(request, job_id):
    """Queue the exact owned snapshot after an explicit, time-bounded confirmation."""

    legacy_error = reject_legacy_session_input(request)
    if legacy_error:
        return legacy_error
    with transaction.atomic():
        job = Job.objects.select_for_update().filter(
            pk=job_id, owner=request.user, kind=JOB_KIND,
        ).first()
        if job is None:
            return error_response("DCC preview was not found.", code="DCC_PREVIEW_NOT_FOUND", response_status=404)
        projects = enabled_projects_by_ids(job.parameters.get("project_ids", ()))
        require_projects_role(request.user, projects, OPERATOR)
        try:
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


def validate_request_values(issue_reference):
    """Reject missing or implausibly large issue references."""

    if not issue_reference:
        return error_response("JIRA task URL is required.", code="DCC_FIELDS_REQUIRED")
    if len(issue_reference) > 2048:
        return error_response("JIRA task URL is too long.", code="DCC_FIELDS_INVALID")
    return None


def reject_legacy_session_input(request):
    """Reject browser credentials outside the canonical JIRA session resource."""

    if not has_legacy_jira_credential((request.data, request.query_params)):
        return None
    return error_response(
        "Connect JIRA through the integrations session endpoint.",
        code="JIRA_SESSION_CANONICAL_REQUIRED",
        response_status=400,
    )
