"""Resolve retained DCC jobs behind immutable CompDoc traces."""

from jobs.models import Job

JOB_KIND = "dcc.create_document"


def latest_jobs_by_trace_source(traces, lock=False):
    """Return the newest retained attempt for each owner and input digest."""

    owner_ids = {trace.confirmed_by_id for trace in traces if trace.confirmed_by_id}
    digests = {trace.job_input_sha256 for trace in traces}
    if not owner_ids or not digests:
        return {}
    jobs = Job.objects.filter(
        kind=JOB_KIND, owner_id__in=owner_ids, input_sha256__in=digests
    )
    if lock:
        jobs = jobs.select_for_update()
    resolved = {}
    for job in jobs.order_by("-attempt", "-created_at"):
        resolved.setdefault((job.owner_id, job.input_sha256), job)
    return resolved
