"""Composition-root resolver for statically allowlisted local executors."""

from django.utils.module_loading import import_string

from automations.catalog import DOORS_QUEUE, LOCAL_QUEUE, executor_kinds, executor_metadata
from jobs.contracts import JobExecutionFailure


def resolve_job_executor(kind):
    """Resolve only local adapters named by the canonical static catalog."""

    metadata = executor_metadata(kind)
    if metadata is None or metadata.queue != LOCAL_QUEUE:
        raise JobExecutionFailure(
            "No worker supports this job type.", "JOB_KIND_UNSUPPORTED"
        )
    try:
        return import_string(metadata.dotted_path)
    except ImportError as error:
        raise JobExecutionFailure(
            "The configured job executor is unavailable.",
            "JOB_EXECUTOR_UNAVAILABLE",
            True,
        ) from error


def local_job_kinds():
    """Return kinds the in-process worker is permitted to claim."""

    return executor_kinds(LOCAL_QUEUE)


def local_job_timeout(kind):
    """Return the catalog timeout for one allowlisted local executor."""

    metadata = executor_metadata(kind)
    if metadata is None or metadata.queue != LOCAL_QUEUE:
        raise JobExecutionFailure(
            "No worker supports this job type.", "JOB_KIND_UNSUPPORTED"
        )
    return metadata.timeout_seconds


def resolve_worker_executor(kind):
    """Resolve local jobs and the explicitly enabled Windows DOORS adapter."""

    metadata = executor_metadata(kind)
    if metadata is None or metadata.queue not in {LOCAL_QUEUE, DOORS_QUEUE}:
        raise JobExecutionFailure(
            "No worker supports this job type.", "JOB_KIND_UNSUPPORTED"
        )
    dotted_path = metadata.dotted_path
    if metadata.queue == DOORS_QUEUE:
        dotted_path = "integrations.doors.job_executor.execute_doors_job"
    try:
        return import_string(dotted_path)
    except ImportError as error:
        raise JobExecutionFailure(
            "The configured job executor is unavailable.",
            "JOB_EXECUTOR_UNAVAILABLE",
            True,
        ) from error


def worker_job_kinds(include_doors=False):
    """Return the queue allowlist selected for one worker process."""

    kinds = list(executor_kinds(LOCAL_QUEUE))
    if include_doors:
        kinds.extend(executor_kinds(DOORS_QUEUE))
    return tuple(kinds)


def worker_job_timeout(kind, include_doors=False):
    """Return a timeout only for a kind this worker may execute."""

    metadata = executor_metadata(kind)
    allowed_queues = {LOCAL_QUEUE, DOORS_QUEUE} if include_doors else {LOCAL_QUEUE}
    if metadata is None or metadata.queue not in allowed_queues:
        raise JobExecutionFailure(
            "No worker supports this job type.", "JOB_KIND_UNSUPPORTED"
        )
    return metadata.timeout_seconds
