"""Composition-root resolver for statically allowlisted local executors."""

from django.utils.module_loading import import_string

from automations.catalog import LOCAL_QUEUE, executor_kinds, executor_metadata
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
