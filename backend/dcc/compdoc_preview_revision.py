"""Create immutable CompDoc-enriched revisions of captured DCC previews."""

import json
from copy import deepcopy
from datetime import timedelta

from django.core.files.base import ContentFile
from django.utils import timezone

from jobs.artifacts import materialize_job_input
from jobs.confirmation import create_confirmation_job
from jobs.models import JobStatus
from jobs.services import record_event, set_job_state

from .compdoc_bridge import (
    MAX_COMPDOC_SELECTION,
    attach_compliance_documents,
    normalize_document_ids,
)
from .compdoc_recommendations import recommend_compdocs
from .document_job import load_snapshot
from .document_preview import prepare_dcc_preview
from .document_snapshot import DccSnapshotError, validate_snapshot_size
from .job_parameters import build_preview_parameters
from .preview_confirmation import preview_expired

JOB_KIND = "dcc.create_document"


def build_compdoc_revision(request, source_job, requested_ids, key, ttl_seconds):
    """Create a child preview from the source's verified JIRA snapshot."""

    validate_revision_source(source_job)
    existing_ids = source_job.parameters.get("compdoc_ids") or []
    combined_ids = combine_document_ids(existing_ids, requested_ids)
    snapshot = read_source_snapshot(source_job)
    snapshot.pop("compliance_documents", None)
    attach_compliance_documents(
        snapshot, request.user, snapshot["project_slug"], combined_ids
    )
    validate_snapshot_size(snapshot)
    return persist_revision(
        request, source_job, snapshot, combined_ids, requested_ids, key, ttl_seconds
    )


def validate_revision_source(source_job):
    """Require one active, unexpired DCC confirmation preview."""

    if source_job.kind != JOB_KIND:
        raise revision_error("Select a DCC document preview.", "DCC_PREVIEW_NOT_FOUND", 404)
    if source_job.status != JobStatus.AWAITING_CONFIRMATION:
        raise revision_error(
            "Only an unconfirmed DCC preview can be enriched.",
            "DCC_PREVIEW_NOT_CONFIRMABLE",
            409,
        )
    if preview_expired(source_job):
        raise revision_error(
            "The DCC preview expired. Capture the JIRA source again.",
            "DCC_PREVIEW_EXPIRED",
            410,
        )


def combine_document_ids(existing_ids, requested_ids):
    """Return a bounded stable union and reject no-op revisions."""

    normalized_existing = normalize_document_ids(existing_ids)
    normalized_requested = normalize_document_ids(requested_ids)
    if not normalized_requested:
        raise revision_error(
            "Select at least one recommended compliance document.",
            "DCC_COMPDOC_SELECTION_REQUIRED",
        )
    combined = sorted(set(normalized_existing).union(normalized_requested))
    if len(combined) > MAX_COMPDOC_SELECTION:
        raise revision_error("Select at most 50 compliance documents.", "DCC_COMPDOC_LIMIT")
    if combined == normalized_existing:
        raise revision_error(
            "The selected compliance documents are already linked.",
            "DCC_COMPDOC_SELECTION_UNCHANGED",
            409,
        )
    return combined


def read_source_snapshot(source_job):
    """Materialize and verify a private source snapshot before reuse."""

    input_path = materialize_job_input(source_job)
    try:
        return deepcopy(load_snapshot(input_path))
    finally:
        input_path.unlink(missing_ok=True)


def persist_revision(
    request, source_job, snapshot, combined_ids, requested_ids, key, ttl_seconds
):
    """Persist a derived confirmation job and supersede its source preview."""

    project_slug = snapshot["project_slug"]
    parameters = build_preview_parameters(snapshot["issue_key"], project_slug, combined_ids)
    parameters["source_preview_id"] = str(source_job.id)
    parameters["requested_compdoc_ids"] = requested_ids
    recommendations = recommend_compdocs(snapshot, request.user, combined_ids)
    summary = prepare_dcc_preview(snapshot, recommendations)
    expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
    job, created = create_confirmation_job(
        request.user, JOB_KIND, source_job.title, parameters,
        snapshot_upload(snapshot), expires_at, summary,
        idempotency_key=key,
        request_id=getattr(request, "request_id", ""),
        source_job=source_job,
    )
    if created:
        try:
            supersede_source_preview(source_job, job, len(combined_ids))
        except Exception:
            delete_revision_artifact(job)
            raise
    return job, created


def delete_revision_artifact(job):
    """Remove a child artifact when the surrounding revision transaction fails."""

    if job.input_file.name:
        job.input_file.storage.delete(job.input_file.name)


def supersede_source_preview(source_job, target_job, document_count):
    """Prevent double confirmation while retaining immutable lineage."""

    source_job.retryable = False
    source_job.save(update_fields=["retryable", "updated_at"])
    set_job_state(
        source_job, JobStatus.CANCELLED, source_job.progress,
        "Superseded by a CompDoc-enriched preview.",
        "DCC_PREVIEW_SUPERSEDED",
    )
    record_event(
        source_job, "CompDoc recommendations applied.",
        "DCC_COMPDOC_RECOMMENDATIONS_APPLIED",
        {"target_job_id": str(target_job.id), "document_count": document_count},
    )
    record_event(
        target_job, "Preview derived from an immutable DCC snapshot.",
        "DCC_PREVIEW_DERIVED",
        {"source_job_id": str(source_job.id), "document_count": document_count},
    )


def snapshot_upload(snapshot):
    """Encode a derived DCC snapshot as a private JSON upload."""

    content = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return ContentFile(content, name=f"dcc-{snapshot['issue_key']}.json")


def revision_error(message, code, response_status=400):
    """Return a stable safe DCC snapshot error."""

    return DccSnapshotError(message, code, response_status)
