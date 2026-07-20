"""Persist confirmed CompDoc provenance independently from job retention."""

from django.utils.dateparse import parse_datetime

from jobs.artifacts import materialize_job_input

from .document_job import load_snapshot
from .models import DccCompdocTrace


def create_traceability_links(job):
    """Persist one immutable audit row per CompDoc in a confirmed DCC snapshot."""

    snapshot = load_job_snapshot(job)
    bundle = snapshot.get("compliance_documents") or {}
    documents = bundle.get("documents") or []
    if not documents:
        return
    traces = [build_trace(job, snapshot, bundle, source) for source in documents]
    DccCompdocTrace.objects.bulk_create(traces)


def load_job_snapshot(job):
    """Materialize and validate the exact private DCC snapshot being confirmed."""

    path = materialize_job_input(job)
    try:
        return load_snapshot(path)
    finally:
        path.unlink(missing_ok=True)


def build_trace(job, snapshot, bundle, source):
    """Build a retention-independent trace row from validated snapshot data."""

    return DccCompdocTrace(
        job_id=job.id,
        job_input_sha256=job.input_sha256,
        confirmed_by=job.owner,
        issue_key=snapshot["issue_key"],
        project_slug=snapshot["project_slug"],
        compdoc_id=source["id"],
        source_history_id=source.get("source_history_id"),
        source_history_at=parse_source_time(source.get("source_history_at")),
        snapshot_fingerprint=bundle["fingerprint"],
    )


def parse_source_time(value):
    """Parse a validated ISO history timestamp without inventing one."""

    return parse_datetime(value) if value else None
