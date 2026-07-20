"""Semantic replay handling for current-source DCC refresh previews."""

from jobs.contracts import JobExecutionFailure
from jobs.models import Job, JobStatus

from .compdoc_confirmation import validate_compdoc_preview_current
from .compdoc_preview_revision import delete_revision_artifact
from .document_snapshot import DccSnapshotError
from .preview_confirmation import preview_expired

JOB_KIND = "dcc.create_document"


def existing_refresh_job(owner, trace):
    """Return a current semantic replay or discard an abandoned stale preview."""

    existing = Job.objects.filter(
        owner=owner,
        kind=JOB_KIND,
        parameters__refreshed_from_trace_id=str(trace.id),
    ).order_by("-created_at").first()
    if not existing or existing.status != JobStatus.AWAITING_CONFIRMATION:
        return existing
    if preview_expired(existing) or preview_source_changed(owner, existing):
        delete_abandoned_preview(existing)
        return None
    return existing


def preview_source_changed(owner, job):
    """Return whether an unconfirmed child is stale or unreadable."""

    try:
        validate_compdoc_preview_current(owner, job)
    except JobExecutionFailure:
        return True
    except DccSnapshotError as error:
        if error.code == "DCC_COMPDOC_SOURCE_CHANGED":
            return True
        raise
    return False


def delete_abandoned_preview(job):
    """Remove a stale child and its private artifact before rebuilding it."""

    delete_revision_artifact(job)
    job.delete()
