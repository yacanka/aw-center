"""Server-side state transitions for the host-local DOORS runner."""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from awcenter.file_security import SAFE_NAME_PATTERN
from jobs.execution import (
    ExecutionLease,
    execution_status,
    heartbeat_interval,
    lease_duration,
    lock_active_execution,
    renew_execution_lease,
    touch_worker,
    update_execution_progress,
)
from jobs.contracts import JobCancelled, JobLeaseLost
from jobs.artifacts import (
    discard_staged_job_output,
    publish_staged_job_output,
    stage_job_output,
)
from jobs.models import JobStatus, WorkerHeartbeat
from jobs.services import set_job_state
from jobs.worker import claim_next_job

from .catalog import DOORS_QUEUE, ExecutorMetadata, executor_kinds, executor_metadata
from .identity import RunnerIdentity, runner_configuration_ready

SHA256_PATTERN = frozenset("0123456789abcdef")
TRANSFER_DIRECTIONS = frozenset({"input", "output"})
FAILURE_CODES = frozenset(
    {
        "DOORS_RUNNER_TASK_FAILED",
        "DOORS_RUNNER_INVALID_INPUT",
        "DOORS_RUNNER_TASK_TIMEOUT",
        "DOORS_RUNNER_SHUTDOWN",
    }
)
STATIC_EXTERNAL_WRITE_KINDS = frozenset({"doors.update_object", "doors.create_object"})
logger = logging.getLogger(__name__)


class RunnerRequestInvalid(APIException):
    status_code = 400
    default_code = "DOORS_RUNNER_REQUEST_INVALID"
    default_detail = "DOORS runner request is invalid."


class RunnerClaimLost(APIException):
    status_code = 409
    default_code = "DOORS_RUNNER_CLAIM_LOST"
    default_detail = "DOORS runner execution claim is no longer active."


class RunnerTransferRejected(APIException):
    status_code = 409
    default_code = "DOORS_RUNNER_TRANSFER_REJECTED"
    default_detail = "DOORS runner artifact transfer was rejected."


class RunnerUnavailable(APIException):
    status_code = 503
    default_code = "DOORS_RUNNER_UNAVAILABLE"
    default_detail = "DOORS runner state is temporarily unavailable."


@dataclass(frozen=True)
class RunnerClaim:
    """Return only execution-scoped data needed by one native DOORS runner."""

    job_id: object
    kind: str
    execution_token: object
    metadata: ExecutorMetadata
    input_name: str
    input_sha256: str
    input_token: str
    output_token: str
    lease_expires_at: object
    heartbeat_interval_seconds: float
    lease_seconds: int


def runner_status() -> dict[str, object]:
    """Return non-secret, fail-closed availability for browser status APIs."""

    configured = runner_configuration_ready()
    stale_seconds = max(5, int(getattr(settings, "JOB_WORKER_STALE_SECONDS", 10)))
    active_runners = 0
    if configured:
        active_since = timezone.now() - timedelta(seconds=stale_seconds)
        try:
            active_runners = WorkerHeartbeat.objects.filter(
                worker_id__startswith="doors:", heartbeat_at__gte=active_since
            ).count()
        except Exception:
            active_runners = 0
    available = configured and active_runners > 0
    return {
        "configured": configured,
        "enabled": available,
        "available": available,
        "active_runners": active_runners,
        "queue": DOORS_QUEUE,
        "transport": "loopback_token",
        "database_access": "none",
        "cache_access": "none",
    }


def runner_poll_interval() -> float:
    """Return the server-selected idle polling cadence for the local runner."""

    stale_seconds = max(5, int(getattr(settings, "JOB_WORKER_STALE_SECONDS", 10)))
    return max(1.0, min(30.0, stale_seconds / 2))


def claim_doors_job(identity: RunnerIdentity) -> RunnerClaim | None:
    """Claim only a catalog-allowlisted DOORS job for one runner identity."""

    kinds = executor_kinds(DOORS_QUEUE)
    touch_worker(identity.worker_id)
    if not kinds:
        return None
    for _attempt in range(10):
        job = claim_next_job(identity.worker_id, kinds)
        if job is None:
            return None
        metadata = executor_metadata(job.kind)
        if metadata is None or metadata.queue != DOORS_QUEUE or not valid_input(job, metadata):
            reject_invalid_claim(job)
            continue
        input_token, output_token = issue_transfer_tokens(job, metadata)
        return RunnerClaim(
            job_id=job.id,
            kind=job.kind,
            execution_token=job.execution_token,
            metadata=metadata,
            input_name=job.input_name,
            input_sha256=job.input_sha256,
            input_token=input_token,
            output_token=output_token,
            lease_expires_at=job.lease_expires_at,
            heartbeat_interval_seconds=heartbeat_interval(),
            lease_seconds=int(lease_duration().total_seconds()),
        )
    raise RunnerUnavailable()


def heartbeat_doors_job(identity, job_id, execution_token, progress=None):
    """Renew and optionally advance one token-bound runner execution claim."""

    lease = build_lease(identity, job_id, execution_token)
    if not renew_execution_lease(lease):
        raise RunnerClaimLost()
    try:
        status = execution_status(lease)
        if progress is not None and status == JobStatus.RUNNING:
            update_execution_progress(
                lease, validate_progress(progress), "DOORS runner is executing the job."
            )
            status = execution_status(lease)
    except (JobCancelled, JobLeaseLost) as error:
        raise RunnerClaimLost() from error
    return {
        "status": status,
        "cancel_requested": status == JobStatus.CANCEL_REQUESTED,
    }


def open_input_artifact(identity, job_id, execution_token, artifact_token):
    """Verify, consume, and open one execution-scoped input artifact exactly once."""

    lease = build_lease(identity, job_id, execution_token)
    with transaction.atomic():
        job = lock_doors_claim(lease)
        require_transfer(job, lease, "input", artifact_token)
    try:
        artifact = job.input_file.open("rb")
        digest = stream_digest(artifact)
        artifact.seek(0)
    except Exception as error:
        mark_corrupt_input(lease, artifact_token)
        raise RunnerTransferRejected() from error
    if not hmac.compare_digest(digest, job.input_sha256):
        artifact.close()
        mark_corrupt_input(lease, artifact_token)
        raise RunnerTransferRejected()
    try:
        with transaction.atomic():
            current = lock_doors_claim(lease)
            consume_transfer(current, lease, "input", artifact_token)
    except Exception:
        artifact.close()
        raise
    return artifact, job.input_name, digest


def complete_doors_job(
    identity,
    job_id,
    execution_token,
    artifact_token,
    completion_status,
    *,
    uploaded_file=None,
    declared_sha256="",
    output_name="",
    failure_code="",
):
    """CAS-publish one terminal result using its single-use output capability."""

    lease = build_lease(identity, job_id, execution_token)
    if completion_status == "succeeded":
        return complete_success(
            lease, artifact_token, uploaded_file, declared_sha256, output_name
        )
    if completion_status not in {"failed", "cancelled"}:
        raise RunnerRequestInvalid()
    with transaction.atomic():
        job = lock_doors_claim(lease, allow_cancel_requested=True)
        consume_transfer(job, lease, "output", artifact_token)
        external_write = (
            job.reconcile_on_lease_loss or job.kind in STATIC_EXTERNAL_WRITE_KINDS
        )
        if external_write and (
            completion_status == "cancelled" or job.status == JobStatus.CANCEL_REQUESTED
        ):
            job.retryable = False
            set_job_state(
                job,
                JobStatus.RECONCILIATION_REQUIRED,
                job.progress,
                "Confirm the external system state before submitting another write.",
                "RECONCILIATION_REQUIRED",
            )
        elif completion_status == "cancelled" or job.status == JobStatus.CANCEL_REQUESTED:
            set_job_state(
                job, JobStatus.CANCELLED, job.progress, "DOORS runner job cancelled.",
                "JOB_CANCELLED",
            )
        else:
            code = failure_code if failure_code in FAILURE_CODES else "DOORS_RUNNER_TASK_FAILED"
            if external_write and code in {
                "DOORS_RUNNER_TASK_TIMEOUT",
                "DOORS_RUNNER_SHUTDOWN",
            }:
                job.retryable = False
                set_job_state(
                    job,
                    JobStatus.RECONCILIATION_REQUIRED,
                    job.progress,
                    "Confirm the external system state before submitting another write.",
                    "RECONCILIATION_REQUIRED",
                )
            else:
                job.retryable = code in {
                    "DOORS_RUNNER_TASK_TIMEOUT",
                    "DOORS_RUNNER_SHUTDOWN",
                }
                set_job_state(
                    job, JobStatus.FAILED, job.progress, "DOORS runner job failed.", code
                )
    return job.status


def complete_success(lease, artifact_token, uploaded_file, declared_sha256, output_name):
    """Stage then fence a remote result so a stale claim cannot publish it."""

    filename = validate_output(uploaded_file, declared_sha256, output_name)
    digest = stream_digest(uploaded_file)
    uploaded_file.seek(0)
    if not hmac.compare_digest(digest, declared_sha256.lower()):
        raise RunnerTransferRejected()

    staged = None
    published = False
    try:
        with transaction.atomic():
            job = lock_doors_claim(lease, allow_cancel_requested=True)
            require_transfer(job, lease, "output", artifact_token)
        staged = stage_job_output(job, filename, uploaded_file)
        if not hmac.compare_digest(staged.digest, digest):
            raise RunnerTransferRejected()
        with transaction.atomic():
            job = lock_doors_claim(lease, allow_cancel_requested=True)
            consume_transfer(job, lease, "output", artifact_token)
            publish_staged_job_output(staged)
            published = True
            job.output_file = staged.final_name
            job.output_name = filename
            job.output_sha256 = staged.digest
            job.result_summary = {"type": "doors_automation"}
            set_job_state(
                job, JobStatus.SUCCEEDED, 100, "DOORS runner job completed."
            )
        return job.status
    except Exception:
        try:
            discard_staged_job_output(staged, published=published)
        except Exception as cleanup_error:
            logger.error(
                "Failed to remove an unpublished runner artifact",
                extra={
                    "job_id": str(lease.job_id),
                    "error_type": type(cleanup_error).__name__,
                },
            )
        raise


def build_lease(identity, job_id, execution_token):
    """Parse public identifiers into the existing jobs fencing contract."""

    try:
        parsed_job_id = UUID(str(job_id))
        parsed_execution_token = UUID(str(execution_token))
    except (TypeError, ValueError, AttributeError) as error:
        raise RunnerRequestInvalid() from error
    return ExecutionLease(parsed_job_id, identity.worker_id, parsed_execution_token)


def lock_doors_claim(lease, *, allow_cancel_requested=False):
    """Lock a live claim and enforce the static DOORS queue allowlist."""

    try:
        job = lock_active_execution(
            lease, allow_cancel_requested=allow_cancel_requested
        )
    except (JobCancelled, JobLeaseLost) as error:
        raise RunnerClaimLost() from error
    metadata = executor_metadata(job.kind)
    if metadata is None or metadata.queue != DOORS_QUEUE:
        raise RunnerClaimLost()
    return job


def valid_input(job, metadata):
    """Reject jobs whose stored input does not match catalog metadata."""

    policy = metadata.upload_policy
    suffix = Path(job.input_name).suffix.lower()
    try:
        size = job.input_file.size
    except (OSError, ValueError):
        return False
    return bool(
        policy
        and suffix in policy.extensions
        and 0 < size <= policy.maximum_bytes
        and valid_sha256(job.input_sha256)
    )


def reject_invalid_claim(job):
    """Fail an invalid allowlisted input without exposing its stored metadata."""

    lease = ExecutionLease.from_job(job)
    with transaction.atomic():
        locked = lock_doors_claim(lease, allow_cancel_requested=True)
        if locked.status == JobStatus.CANCEL_REQUESTED:
            set_job_state(
                locked, JobStatus.CANCELLED, locked.progress, "Job cancelled.",
                "JOB_CANCELLED",
            )
        else:
            locked.retryable = False
            set_job_state(
                locked,
                JobStatus.FAILED,
                locked.progress,
                "DOORS runner input is invalid.",
                "DOORS_RUNNER_INVALID_INPUT",
            )


def issue_transfer_tokens(job, metadata):
    """Issue two opaque capabilities scoped to one execution token and direction."""

    input_token = secrets.token_urlsafe(32)
    output_token = secrets.token_urlsafe(32)
    timeout = max(300, min(86400, metadata.timeout_seconds + 120))
    issued = []
    try:
        for direction, token in (("input", input_token), ("output", output_token)):
            key = transfer_key(job.id, job.execution_token, direction, token, "issued")
            cache.set(key, job.worker_id, timeout=timeout)
            if cache.get(key) != job.worker_id:
                raise RunnerUnavailable()
            issued.append(key)
    except Exception as error:
        for key in issued:
            try:
                cache.delete(key)
            except Exception:
                pass
        requeue_dispatch_failure(job)
        if isinstance(error, RunnerUnavailable):
            raise
        raise RunnerUnavailable() from error
    return input_token, output_token


def requeue_dispatch_failure(job):
    """Release a claim when server-side transfer state could not be created."""

    lease = ExecutionLease.from_job(job)
    with transaction.atomic():
        locked = lock_doors_claim(lease, allow_cancel_requested=True)
        if locked.status == JobStatus.CANCEL_REQUESTED:
            set_job_state(
                locked, JobStatus.CANCELLED, locked.progress, "Job cancelled.",
                "JOB_CANCELLED",
            )
        else:
            set_job_state(
                locked,
                JobStatus.QUEUED,
                locked.progress,
                "DOORS runner dispatch will retry.",
            )


def require_transfer(job, lease, direction, token):
    """Verify an issued execution capability without consuming it."""

    validate_transfer_token(direction, token)
    issued_key = transfer_key(job.id, lease.token, direction, token, "issued")
    consumed_key = transfer_key(job.id, lease.token, direction, token, "consumed")
    try:
        owner = cache.get(issued_key)
        consumed = cache.get(consumed_key)
    except Exception as error:
        raise RunnerUnavailable() from error
    if consumed or not owner or not hmac.compare_digest(str(owner), lease.worker_id):
        raise RunnerTransferRejected()


def consume_transfer(job, lease, direction, token):
    """Atomically consume a capability while its database claim row is locked."""

    require_transfer(job, lease, direction, token)
    issued_key = transfer_key(job.id, lease.token, direction, token, "issued")
    consumed_key = transfer_key(job.id, lease.token, direction, token, "consumed")
    try:
        consumed = cache.add(consumed_key, lease.worker_id, timeout=86400)
        if consumed:
            cache.delete(issued_key)
    except Exception as error:
        raise RunnerUnavailable() from error
    if not consumed:
        raise RunnerTransferRejected()


def transfer_key(job_id, execution_token, direction, token, state):
    """Build a non-secret cache key from a capability digest."""

    token_digest = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
    return f"awc:doors-runner:v1:{job_id}:{execution_token}:{direction}:{state}:{token_digest}"


def validate_transfer_token(direction, token):
    if direction not in TRANSFER_DIRECTIONS:
        raise RunnerTransferRejected()
    normalized = str(token or "")
    if len(normalized) < 32 or len(normalized) > 128:
        raise RunnerTransferRejected()


def validate_output(uploaded_file, declared_sha256, output_name):
    """Validate remote result bounds and traversal-safe display name."""

    if uploaded_file is None or uploaded_file.size < 1:
        raise RunnerRequestInvalid()
    if uploaded_file.size > maximum_output_bytes():
        raise RunnerRequestInvalid()
    filename = str(output_name or uploaded_file.name or "").strip()
    if (
        not filename
        or len(filename) > 180
        or Path(filename).name != filename
        or not SAFE_NAME_PATTERN.fullmatch(filename)
        or not valid_sha256(declared_sha256)
    ):
        raise RunnerRequestInvalid()
    return filename


def maximum_output_bytes():
    """Return the effective multipart and job-artifact output ceiling."""

    job_limit = int(getattr(settings, "JOB_MAX_OUTPUT_BYTES", 1024**3))
    request_limit = int(
        getattr(settings, "AWCENTER_ABSOLUTE_MAX_UPLOAD_BYTES", job_limit)
    )
    return min(job_limit, request_limit)


def validate_progress(value):
    try:
        progress = int(value)
    except (TypeError, ValueError) as error:
        raise RunnerRequestInvalid() from error
    if not 0 <= progress <= 99:
        raise RunnerRequestInvalid()
    return progress


def valid_sha256(value):
    normalized = str(value or "").lower()
    return len(normalized) == 64 and set(normalized) <= SHA256_PATTERN


def stream_digest(file_object):
    digest = hashlib.sha256()
    for chunk in iter(lambda: file_object.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def mark_corrupt_input(lease, artifact_token):
    """Terminally fence a stored input that fails its persisted SHA-256 contract."""

    try:
        with transaction.atomic():
            job = lock_doors_claim(lease, allow_cancel_requested=True)
            consume_transfer(job, lease, "input", artifact_token)
            if job.status == JobStatus.CANCEL_REQUESTED:
                set_job_state(
                    job, JobStatus.CANCELLED, job.progress, "Job cancelled.",
                    "JOB_CANCELLED",
                )
            else:
                job.retryable = False
                set_job_state(
                    job,
                    JobStatus.FAILED,
                    job.progress,
                    "Stored input failed integrity verification.",
                    "JOB_INPUT_CORRUPT",
                )
    except (RunnerClaimLost, RunnerTransferRejected):
        return
