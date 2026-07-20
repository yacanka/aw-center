"""HTTP endpoint for credential-free current-CompDoc DCC revisions."""

import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from jobs.api import job_creation_response
from jobs.services import IdempotencyConflict, validate_idempotency_key

from common.compdoc_versions import latest_history_id

from .compdoc_bridge import require_model_view_permission, resolve_compdoc_model
from .compdoc_changes import load_trace_source_changes
from .compdoc_job_sources import latest_jobs_by_trace_source
from .compdoc_refresh import (
    build_refreshed_preview,
    refresh_availability,
    refresh_error,
)
from .compdoc_refresh_replay import existing_refresh_job
from .document_snapshot import DccSnapshotError
from .job_error_responses import snapshot_error_response, unexpected_capture_response
from .job_views import preview_ttl_seconds
from .models import DccCompdocTrace
from .permissions import DCCTraceRefreshPermission

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated, DCCTraceRefreshPermission])
def refresh_compdoc_trace_preview(request, trace_id):
    """Create or replay a current-source preview from one owned retained trace."""

    try:
        key = validate_idempotency_key(request.headers.get("Idempotency-Key", ""))
        with transaction.atomic():
            trace = owned_locked_trace(request.user, trace_id)
            model, document = authorized_document(request.user, trace)
            existing = existing_refresh_job(request.user, trace)
            if existing:
                return job_creation_response(existing, False)
            source_job = refresh_source_job(trace)
            source_change = load_trace_source_changes(model, document, [trace])[trace.id]
            availability = refresh_availability(
                trace, source_job, latest_history_id(model, document.pk),
                source_change, request.user.id,
            )
            require_refresh_ready(availability)
            job, created = build_refreshed_preview(
                request, trace, source_job, key, preview_ttl_seconds()
            )
        return job_creation_response(job, created)
    except DccSnapshotError as error:
        return snapshot_error_response(error)
    except IdempotencyConflict:
        raise
    except Exception:
        return unexpected_capture_response(logger)


def owned_locked_trace(user, trace_id):
    """Return an owned trace without disclosing another user's provenance."""

    trace = DccCompdocTrace.objects.select_for_update().filter(
        id=trace_id, confirmed_by=user
    ).first()
    if trace is None:
        raise refresh_error(
            "DCC trace was not found.", "DCC_COMPDOC_REFRESH_TRACE_NOT_FOUND", 404
        )
    return trace


def authorized_document(user, trace):
    """Resolve the concrete project and require current CompDoc read access."""

    _project, model = resolve_compdoc_model(trace.project_slug)
    require_model_view_permission(user, model)
    return model, get_object_or_404(model, pk=trace.compdoc_id)


def refresh_source_job(trace):
    """Lock and return the newest retained job attempt behind a trace."""

    jobs = latest_jobs_by_trace_source([trace], lock=True)
    return jobs.get((trace.confirmed_by_id, trace.job_input_sha256))


def require_refresh_ready(availability):
    """Map a non-ready refresh state to a stable actionable API error."""

    if availability == "ready":
        return
    if availability in {"current", "no_visible_change"}:
        raise refresh_error(
            "DCC-visible compliance document fields are already current.",
            "DCC_COMPDOC_REFRESH_NOT_REQUIRED",
            409,
        )
    if availability == "source_active":
        raise refresh_error(
            "The source DCC job is still active.",
            "DCC_COMPDOC_REFRESH_SOURCE_ACTIVE",
            409,
        )
    raise refresh_error(
        "The original DCC snapshot is no longer available.",
        "DCC_COMPDOC_REFRESH_SOURCE_ARCHIVED",
        410,
    )
