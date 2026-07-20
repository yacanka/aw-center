"""Create a current CompDoc revision from a retained confirmed DCC snapshot."""

from datetime import timedelta

from django.utils import timezone

from jobs.confirmation import create_confirmation_job
from jobs.contracts import JobExecutionFailure
from jobs.models import JobStatus
from jobs.services import record_event

from .compdoc_bridge import attach_compliance_documents, normalize_document_ids
from .compdoc_preview_revision import (
    delete_revision_artifact,
    read_source_snapshot,
    snapshot_upload,
)
from .compdoc_recommendations import recommend_compdocs
from .document_preview import prepare_dcc_preview
from .document_snapshot import DccSnapshotError, validate_snapshot_size
from .job_parameters import build_preview_parameters

JOB_KIND = "dcc.create_document"
ACTIVE_SOURCE_STATUSES = {
    JobStatus.AWAITING_CONFIRMATION,
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
}
TERMINAL_SOURCE_STATUSES = {JobStatus.CANCELLED, JobStatus.SUCCEEDED, JobStatus.FAILED}


def refresh_availability(
    trace, source_job, current_history_id, source_change, requester_id, can_create=True
):
    """Return a stable reason describing whether a trace can create a refresh preview."""

    if trace.source_history_id == current_history_id:
        return "current"
    if source_change["comparison_status"] == "unchanged":
        return "no_visible_change"
    if trace.confirmed_by_id != requester_id:
        return "owner_required"
    if not can_create:
        return "permission_required"
    if not source_job or not source_job.input_file.name:
        return "source_archived"
    if source_job.status in ACTIVE_SOURCE_STATUSES:
        return "source_active"
    return "ready" if source_job.status in TERMINAL_SOURCE_STATUSES else "source_archived"


def build_refreshed_preview(request, trace, source_job, key, ttl_seconds):
    """Rebuild all linked CompDocs from current records without another JIRA read."""

    snapshot = load_refresh_snapshot(source_job)
    document_ids = validate_refresh_lineage(snapshot, trace, source_job)
    previous_fingerprint = trace.snapshot_fingerprint
    snapshot.pop("compliance_documents", None)
    attach_compliance_documents(snapshot, request.user, trace.project_slug, document_ids)
    validate_snapshot_size(snapshot)
    if snapshot["compliance_documents"]["fingerprint"] == previous_fingerprint:
        raise refresh_error(
            "DCC-visible compliance document fields are already current.",
            "DCC_COMPDOC_REFRESH_NOT_REQUIRED",
            409,
        )
    return persist_refreshed_preview(
        request, trace, source_job, snapshot, document_ids, key, ttl_seconds
    )


def load_refresh_snapshot(source_job):
    """Load an integrity-checked retained snapshot or return a recoverable archive error."""

    try:
        return read_source_snapshot(source_job)
    except (OSError, ValueError, JobExecutionFailure) as error:
        raise refresh_error(
            "The original DCC snapshot is no longer available.",
            "DCC_COMPDOC_REFRESH_SOURCE_ARCHIVED",
            410,
        ) from error


def validate_refresh_lineage(snapshot, trace, source_job):
    """Prove the retained snapshot is the exact DCC source represented by the trace."""

    bundle = snapshot.get("compliance_documents") or {}
    raw_ids = [document.get("id") for document in bundle.get("documents") or []]
    try:
        document_ids = normalize_document_ids(raw_ids)
    except DccSnapshotError as error:
        raise invalid_refresh_source() from error
    valid = all(
        (
            source_job.input_sha256 == trace.job_input_sha256,
            snapshot.get("issue_key") == trace.issue_key,
            snapshot.get("project_slug") == trace.project_slug,
            bundle.get("fingerprint") == trace.snapshot_fingerprint,
            str(trace.compdoc_id) in document_ids,
        )
    )
    if not valid:
        raise invalid_refresh_source()
    return document_ids


def persist_refreshed_preview(
    request, trace, source_job, snapshot, document_ids, key, ttl_seconds
):
    """Persist a derived preview with content-free lineage and audit events."""

    parameters = build_preview_parameters(
        snapshot["issue_key"], snapshot["project_slug"], document_ids
    )
    parameters.update(refresh_parameters(trace, source_job))
    recommendations = recommend_compdocs(snapshot, request.user, document_ids)
    summary = prepare_dcc_preview(snapshot, recommendations)
    summary["compdoc_refresh"] = refresh_summary(trace, source_job, len(document_ids))
    expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
    job, created = create_confirmation_job(
        request.user, JOB_KIND, f"Refresh DCC for {trace.issue_key}", parameters,
        snapshot_upload(snapshot), expires_at, summary, key,
        getattr(request, "request_id", ""), source_job,
    )
    if created:
        try:
            record_refresh_events(source_job, job, trace, len(document_ids))
        except Exception:
            delete_revision_artifact(job)
            raise
    return job, created


def refresh_parameters(trace, source_job):
    """Return private job parameters proving refresh lineage."""

    return {
        "refreshed_from_trace_id": str(trace.id),
        "refreshed_from_job_id": str(source_job.id),
    }


def refresh_summary(trace, source_job, document_count):
    """Return safe lineage metadata for explicit human confirmation."""

    return {
        "source_trace_id": str(trace.id),
        "source_job_id": str(source_job.id),
        "document_count": document_count,
    }


def record_refresh_events(source_job, target_job, trace, document_count):
    """Record immutable, content-free lineage on source and target jobs."""

    details = {"target_job_id": str(target_job.id), "document_count": document_count}
    record_event(
        source_job, "Current CompDoc refresh preview created.",
        "DCC_COMPDOC_REFRESH_CREATED", details,
    )
    record_event(
        target_job, "Preview derived from a confirmed DCC snapshot.",
        "DCC_COMPDOC_REFRESH_DERIVED",
        {"source_job_id": str(source_job.id), "source_trace_id": str(trace.id)},
    )


def invalid_refresh_source():
    """Return a safe mismatch error for inconsistent retained lineage."""

    return refresh_error(
        "The retained DCC source does not match this trace.",
        "DCC_COMPDOC_REFRESH_SOURCE_INVALID",
        409,
    )


def refresh_error(message, code, response_status):
    """Create one stable DCC refresh validation error."""

    return DccSnapshotError(message, code, response_status)
