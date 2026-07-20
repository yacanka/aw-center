"""HTTP endpoint for human-selected DCC CompDoc recommendations."""

import logging

from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from awcenter.api_errors import error_response
from jobs.api import job_creation_response
from jobs.contracts import JobExecutionFailure
from jobs.models import Job
from jobs.services import IdempotencyConflict, find_idempotent_job, validate_idempotency_key

from .compdoc_bridge import (
    MAX_COMPDOC_SELECTION,
    normalize_document_ids,
    validate_compdoc_job_access,
)
from .compdoc_preview_revision import JOB_KIND, build_compdoc_revision
from .document_snapshot import DccSnapshotError
from .job_error_responses import snapshot_error_response, unexpected_capture_response
from .job_views import preview_ttl_seconds
from .permissions import DCCAutomationPermission

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCAutomationPermission])
def apply_compdoc_recommendations(request, job_id):
    """Derive a new preview without another JIRA read or source mutation."""

    try:
        requested_ids = parse_requested_ids(request.data)
        key = validate_idempotency_key(request.headers.get("Idempotency-Key", ""))
        with transaction.atomic():
            source = owned_locked_job(request.user, job_id)
            existing = find_idempotent_job(request.user, JOB_KIND, key)
            if existing:
                return replay_revision(source, existing, requested_ids)
            job, created = build_compdoc_revision(
                request, source, requested_ids, key, preview_ttl_seconds()
            )
        return job_creation_response(job, created)
    except DccSnapshotError as error:
        return snapshot_error_response(error)
    except JobExecutionFailure as error:
        return error_response(str(error), code=error.code, response_status=409)
    except IdempotencyConflict:
        raise
    except Exception:
        return unexpected_capture_response(logger)


def parse_requested_ids(payload):
    """Require a list before UUID normalization."""

    raw_ids = payload.get("compdoc_ids") if hasattr(payload, "get") else None
    if not isinstance(raw_ids, list):
        raise DccSnapshotError(
            "Select compliance documents as a list.", "DCC_COMPDOC_IDS_INVALID"
        )
    if len(raw_ids) > MAX_COMPDOC_SELECTION:
        raise DccSnapshotError(
            "Select at most 50 compliance documents.", "DCC_COMPDOC_LIMIT"
        )
    return normalize_document_ids(raw_ids)


def owned_locked_job(user, job_id):
    """Return one locked owned job without exposing cross-owner existence."""

    job = Job.objects.select_for_update().filter(owner=user, pk=job_id).first()
    if job is None:
        raise DccSnapshotError(
            "DCC preview was not found.", "DCC_PREVIEW_NOT_FOUND", 404
        )
    return job


def replay_revision(source, existing, requested_ids):
    """Replay only the exact derived selection for the exact source preview."""

    parameters = existing.parameters
    if existing.source_job_id != source.id:
        raise IdempotencyConflict()
    if parameters.get("requested_compdoc_ids") != requested_ids:
        raise IdempotencyConflict()
    validate_compdoc_job_access(source.owner, parameters)
    return job_creation_response(existing, False)
