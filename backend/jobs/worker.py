"""Durable job claiming, dispatch, fenced publication, and lease recovery."""

import logging
import multiprocessing
from pathlib import Path
from time import monotonic
from uuid import uuid4

from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone

from .contracts import (
    JobCancelled,
    JobExecutionFailure,
    JobExecutionUncertain,
    JobLeaseLost,
)
from .artifacts import (
    discard_staged_job_output,
    publish_staged_job_output,
    stage_job_output,
)
from .execution import (
    ExecutionHeartbeat,
    bind_execution,
    cancellation_requested,
    current_execution_lease,
    execution_status,
    lease_deadline,
    lease_duration,
    lock_active_execution,
    touch_worker,
    update_progress,
)
from .models import Job, JobStatus
from .services import record_event, set_job_state

logger = logging.getLogger(__name__)

CHILD_POLL_SECONDS = 0.1

__all__ = ["claim_next_job", "execute_claimed_job", "recover_expired_jobs", "update_progress"]


def claim_next_job(worker_id, eligible_kinds=None):
    """Atomically lease the oldest queued job to one unique execution claim."""

    from .workflow_controls import reconcile_active_workflows

    reconcile_active_workflows()
    recover_expired_jobs()
    if eligible_kinds is not None and not eligible_kinds:
        touch_worker(worker_id)
        return None
    with transaction.atomic():
        jobs = Job.objects.select_for_update().filter(status=JobStatus.QUEUED)
        if eligible_kinds is not None:
            jobs = jobs.filter(kind__in=tuple(eligible_kinds))
        job = jobs.order_by("created_at").first()
        if not job:
            touch_worker(worker_id)
            return None
        job.status = JobStatus.RUNNING
        job.started_at = job.started_at or timezone.now()
        job.worker_id = worker_id
        job.execution_token = uuid4()
        job.lease_expires_at = lease_deadline()
        job.message = "Worker started the job."
        job.save()
        record_event(job, job.message)
        from .workflow_services import synchronize_workflow_job

        synchronize_workflow_job(job)
        touch_worker(worker_id, job)
    logger.info(
        "Job claim started",
        extra={
            "event": "job_started",
            "job_id": str(job.id),
            "job_kind": job.kind,
            "attempt": job.attempt,
            "worker_id": job.worker_id,
            "execution_id": str(job.execution_token),
            "request_id": job.request_id or "-",
        },
    )
    return job


def execute_claimed_job(
    job,
    resolve_executor,
    *,
    timeout_seconds=None,
    isolate=False,
):
    """Dispatch one claimed job and CAS-persist its terminal state."""

    result = None
    with bind_execution(job) as lease:
        heartbeat = ExecutionHeartbeat(lease)
        child = None
        try:
            if isolate:
                child = start_executor_process(job, resolve_executor)
                await_executor_ready(job, lease, child)
                heartbeat.start()
                result = await_executor_process(
                    job,
                    lease,
                    child,
                    execution_timeout(timeout_seconds),
                )
            else:
                heartbeat.start()
                executor = resolve_executor(job.kind)
                result = executor(job)
            if cancellation_requested(job.id) and not job.reconcile_on_lease_loss:
                raise JobCancelled()
            persist_result(
                job.id,
                result,
                allow_cancel_requested=job.reconcile_on_lease_loss,
            )
        except JobLeaseLost:
            stop_executor_process(child)
            log_lost_claim(job)
        except JobCancelled:
            stop_executor_process(child)
            if job.reconcile_on_lease_loss:
                publish_terminal(
                    mark_reconciliation_required,
                    job,
                    "Confirm the external system state before submitting another write.",
                    "RECONCILIATION_REQUIRED",
                )
            else:
                publish_terminal(mark_cancelled, job)
        except JobExecutionUncertain as error:
            stop_executor_process(child)
            publish_terminal(mark_reconciliation_required, job, str(error), error.code)
        except JobExecutionFailure as error:
            stop_executor_process(child)
            if external_write_cancel_requested(job):
                publish_terminal(
                    mark_reconciliation_required,
                    job,
                    "Confirm the external system state before submitting another write.",
                    "RECONCILIATION_REQUIRED",
                )
            else:
                publish_terminal(mark_failed, job, str(error), error.code, error.retryable)
        except Exception as error:
            stop_executor_process(child)
            logger.error(
                "Unhandled job failure: %s",
                type(error).__name__,
                extra={"job_id": str(job.id), "error_type": type(error).__name__},
            )
            if job.reconcile_on_lease_loss:
                publish_terminal(
                    mark_reconciliation_required,
                    job,
                    "Confirm the external system state before submitting another write.",
                    "RECONCILIATION_REQUIRED",
                )
            else:
                publish_terminal(
                    mark_failed,
                    job,
                    "The worker could not complete this job.",
                    "JOB_EXECUTION_FAILED",
                    True,
                )
        finally:
            heartbeat.stop()
            close_executor_process(child)
            if result and result.path.exists():
                result.path.unlink(missing_ok=True)


def start_executor_process(job, resolve_executor):
    """Fork one executor before heartbeat threads start and return its control pipe."""

    try:
        context = multiprocessing.get_context("fork")
    except ValueError as error:
        raise JobExecutionFailure(
            "This worker platform cannot isolate job executors.",
            "JOB_ISOLATION_UNAVAILABLE",
        ) from error
    parent_connection, child_connection = context.Pipe(duplex=False)
    connections.close_all()
    process = context.Process(
        target=execute_in_child,
        args=(job.id, job.kind, resolve_executor, child_connection),
        name=f"job-executor-{str(job.id)[:8]}",
        daemon=False,
    )
    try:
        process.start()
    except Exception:
        parent_connection.close()
        child_connection.close()
        raise
    child_connection.close()
    connections.close_all()
    return ExecutorProcess(process, parent_connection)


class ExecutorProcess:
    """Hold the isolated executor process and its one-way result channel."""

    def __init__(self, process, connection):
        self.process = process
        self.connection = connection


def execute_in_child(job_id, kind, resolve_executor, connection):
    """Run one allowlisted executor and send only a bounded result envelope."""

    connections.close_all()
    try:
        job = Job.objects.get(pk=job_id)
        with bind_execution(job):
            connection.send({"outcome": "ready"})
            executor = resolve_executor(kind)
            result = executor(job)
        connection.send(
            {
                "outcome": "succeeded",
                "result": {
                    "path": str(result.path),
                    "filename": result.filename,
                    "message": result.message,
                    "summary": result.summary,
                },
            }
        )
    except JobCancelled:
        connection.send({"outcome": "cancelled"})
    except JobLeaseLost:
        connection.send({"outcome": "lease_lost"})
    except JobExecutionUncertain as error:
        connection.send(
            {"outcome": "uncertain", "message": str(error), "code": error.code}
        )
    except JobExecutionFailure as error:
        connection.send(
            {
                "outcome": "failed",
                "message": str(error),
                "code": error.code,
                "retryable": error.retryable,
            }
        )
    except BaseException as error:
        connection.send({"outcome": "unhandled", "error_type": type(error).__name__})
    finally:
        connection.close()
        connections.close_all()


def await_executor_ready(job, lease, child):
    """Wait for the child to open its own DB connection before parent heartbeats."""

    deadline = monotonic() + min(10.0, lease_duration().total_seconds() / 2)
    while monotonic() < deadline:
        if child.connection.poll(CHILD_POLL_SECONDS):
            envelope = child.connection.recv()
            if isinstance(envelope, dict) and envelope.get("outcome") == "ready":
                return
            decode_child_outcome(job, lease, envelope)
        if not child.process.is_alive():
            if child.connection.poll():
                decode_child_outcome(job, lease, child.connection.recv())
            break
    stop_executor_process(child)
    if job.reconcile_on_lease_loss:
        raise JobExecutionUncertain()
    raise JobExecutionFailure(
        "The isolated executor could not start.",
        "JOB_EXECUTOR_START_FAILED",
        True,
    )


def await_executor_process(job, lease, child, timeout_seconds):
    """Monitor an executor while the parent owns heartbeat, cancellation, and timeout."""

    deadline = monotonic() + timeout_seconds
    while True:
        if child.connection.poll(CHILD_POLL_SECONDS):
            envelope = child.connection.recv()
            child.process.join(timeout=1)
            return decode_child_outcome(job, lease, envelope)
        if not child.process.is_alive():
            child.process.join(timeout=1)
            if child.connection.poll():
                return decode_child_outcome(job, lease, child.connection.recv())
            if job.reconcile_on_lease_loss:
                raise JobExecutionUncertain()
            raise JobExecutionFailure(
                "The isolated executor stopped unexpectedly.",
                "JOB_EXECUTOR_CRASHED",
                True,
            )
        status = execution_status(lease)
        if status == JobStatus.CANCEL_REQUESTED and not job.reconcile_on_lease_loss:
            stop_executor_process(child)
            raise JobCancelled()
        if monotonic() >= deadline:
            stop_executor_process(child)
            if job.reconcile_on_lease_loss:
                raise JobExecutionUncertain()
            raise JobExecutionFailure(
                "The job exceeded its execution time limit.",
                "JOB_EXECUTION_TIMEOUT",
                True,
            )


def decode_child_outcome(job, lease, envelope):
    """Convert a child envelope into the existing sanitized executor contracts."""

    outcome = envelope.get("outcome") if isinstance(envelope, dict) else ""
    if outcome == "succeeded":
        payload = envelope.get("result") or {}
        from .contracts import JobExecutionResult

        return JobExecutionResult(
            path=Path(payload.get("path", "")),
            filename=str(payload.get("filename", "")),
            message=str(payload.get("message", "Completed successfully.")),
            summary=payload.get("summary"),
        )
    if outcome == "cancelled":
        if job.reconcile_on_lease_loss:
            raise JobExecutionUncertain()
        raise JobCancelled()
    if outcome == "lease_lost":
        raise JobLeaseLost()
    if outcome == "uncertain":
        raise JobExecutionUncertain(str(envelope.get("message") or ""))
    if outcome == "failed":
        if job.reconcile_on_lease_loss and execution_status(lease) == JobStatus.CANCEL_REQUESTED:
            raise JobExecutionUncertain()
        raise JobExecutionFailure(
            str(envelope.get("message") or "The executor failed."),
            str(envelope.get("code") or "JOB_EXECUTION_FAILED"),
            bool(envelope.get("retryable", False)),
        )
    if job.reconcile_on_lease_loss:
        raise JobExecutionUncertain()
    raise JobExecutionFailure(
        "The isolated executor stopped unexpectedly.",
        "JOB_EXECUTOR_CRASHED",
        True,
    )


def stop_executor_process(child):
    """Terminate and reap an executor without leaving an orphan process."""

    if child is None or not child.process.is_alive():
        return
    child.process.terminate()
    child.process.join(timeout=5)
    if child.process.is_alive() and hasattr(child.process, "kill"):
        child.process.kill()
        child.process.join(timeout=5)


def close_executor_process(child):
    """Close parent process resources after normal or forced completion."""

    if child is None:
        return
    stop_executor_process(child)
    child.connection.close()
    try:
        child.process.close()
    except ValueError:
        pass


def execution_timeout(value):
    """Validate a composition-provided catalog timeout with a safe upper bound."""

    if value is None:
        value = getattr(settings, "JOB_EXECUTION_TIMEOUT_SECONDS", 900)
    try:
        seconds = float(value)
    except (TypeError, ValueError) as error:
        raise JobExecutionFailure(
            "The executor timeout is invalid.", "JOB_TIMEOUT_INVALID"
        ) from error
    if seconds <= 0 or seconds > 86400:
        raise JobExecutionFailure(
            "The executor timeout is invalid.", "JOB_TIMEOUT_INVALID"
        )
    return seconds


def external_write_cancel_requested(job):
    """Return cancellation intent only when an external-write claim remains current."""

    if not job.reconcile_on_lease_loss:
        return False
    try:
        return cancellation_requested(job.id)
    except JobLeaseLost:
        return True


def publish_terminal(callback, job, *args):
    """Ignore a terminal transition when recovery has replaced the claim."""

    try:
        callback(job.id, *args)
    except JobLeaseLost:
        log_lost_claim(job)


def log_lost_claim(job):
    """Record a bounded operational signal without exposing executor details."""

    logger.warning(
        "Discarded publication from a stale job claim",
        extra={"job_id": str(job.id), "worker_id": job.worker_id},
    )


def persist_result(job_id, result, *, allow_cancel_requested=False):
    """Stage, fence, and atomically publish one owned result artifact."""

    lease = current_execution_lease(job_id)
    staged = None
    published = False
    try:
        validate_result_artifact(result.path)
        with transaction.atomic():
            job = lock_active_execution(
                lease, allow_cancel_requested=allow_cancel_requested
            )
        with result.path.open("rb") as source:
            staged = stage_job_output(job, result.filename, source)
        with transaction.atomic():
            job = lock_active_execution(
                lease, allow_cancel_requested=allow_cancel_requested
            )
            publish_staged_job_output(staged)
            published = True
            job.output_file = staged.final_name
            job.output_sha256 = staged.digest
            job.output_name = result.filename
            job.result_summary = result.summary or {}
            set_job_state(job, JobStatus.SUCCEEDED, 100, result.message)
    except Exception:
        try:
            discard_staged_job_output(staged, published=published)
        except Exception as cleanup_error:
            logger.error(
                "Failed to remove an unpublished job artifact",
                extra={
                    "job_id": str(job_id),
                    "error_type": type(cleanup_error).__name__,
                },
            )
        raise
    finally:
        result.path.unlink(missing_ok=True)


def validate_result_artifact(path):
    """Reject absent, empty, or oversized executor output."""

    size = path.stat().st_size if path.exists() else 0
    if size == 0:
        raise JobExecutionFailure("The executor produced no output.", "JOB_OUTPUT_MISSING")
    if size > settings.JOB_MAX_OUTPUT_BYTES:
        raise JobExecutionFailure(
            "Generated output exceeds the safety limit.", "JOB_OUTPUT_TOO_LARGE"
        )


def mark_cancelled(job_id):
    """CAS-persist a cooperative cancellation terminal state."""

    lease = current_execution_lease(job_id)
    with transaction.atomic():
        job = lock_active_execution(lease, allow_cancel_requested=True)
        set_job_state(job, JobStatus.CANCELLED, job.progress, "Job cancelled.", "JOB_CANCELLED")


def mark_failed(job_id, message, code, retryable=False):
    """CAS-persist a sanitized terminal failure."""

    lease = current_execution_lease(job_id)
    with transaction.atomic():
        job = lock_active_execution(lease, allow_cancel_requested=True)
        if job.status == JobStatus.CANCEL_REQUESTED:
            set_job_state(
                job, JobStatus.CANCELLED, job.progress, "Job cancelled.", "JOB_CANCELLED"
            )
            return
        job.retryable = retryable
        set_job_state(job, JobStatus.FAILED, job.progress, message, code)


def mark_reconciliation_required(job_id, message, code):
    """Persist an ambiguous external-write outcome without allowing retries."""

    lease = current_execution_lease(job_id)
    with transaction.atomic():
        job = lock_active_execution(lease, allow_cancel_requested=True)
        job.retryable = False
        set_job_state(
            job,
            JobStatus.RECONCILIATION_REQUIRED,
            job.progress,
            message,
            code,
        )


def recover_expired_jobs():
    """Requeue jobs abandoned after a worker lease expired."""

    statuses = [JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED]
    job_ids = Job.objects.filter(
        status__in=statuses, lease_expires_at__lt=timezone.now()
    ).values_list("id", flat=True)[:100]
    for job_id in list(job_ids):
        recover_expired_job(job_id)


def recover_expired_job(job_id):
    """Recover one expired claim under a row lock and invalidate its token."""

    with transaction.atomic():
        try:
            job = Job.objects.select_for_update().get(pk=job_id)
        except Job.DoesNotExist:
            return
        if job.status not in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
            return
        if not job.lease_expires_at or job.lease_expires_at >= timezone.now():
            return
        if job.status == JobStatus.CANCEL_REQUESTED and job.reconcile_on_lease_loss:
            job.retryable = False
            set_job_state(
                job,
                JobStatus.RECONCILIATION_REQUIRED,
                job.progress,
                "Confirm the external system state before submitting another write.",
                "RECONCILIATION_REQUIRED",
            )
        elif job.status == JobStatus.CANCEL_REQUESTED:
            set_job_state(job, JobStatus.CANCELLED, job.progress, "Job cancelled.", "JOB_CANCELLED")
        elif job.reconcile_on_lease_loss:
            job.retryable = False
            set_job_state(
                job,
                JobStatus.RECONCILIATION_REQUIRED,
                job.progress,
                "Confirm the external system state before submitting another write.",
                "RECONCILIATION_REQUIRED",
            )
        elif job.attempt >= job.max_attempts:
            set_job_state(
                job,
                JobStatus.FAILED,
                job.progress,
                "Worker lease expired.",
                "JOB_LEASE_EXPIRED",
            )
        else:
            job.attempt += 1
            job.lease_expires_at = None
            job.worker_id = ""
            job.execution_token = None
            set_job_state(
                job, JobStatus.QUEUED, job.progress, "Recovered after worker interruption."
            )
