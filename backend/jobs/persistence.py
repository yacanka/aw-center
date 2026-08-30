"""Workflow-agnostic persistence primitives for durable jobs and artifacts."""

import hashlib
import re

from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, ValidationError

from .models import Job, JobEvent

IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class IdempotencyConflict(APIException):
    """Reject reuse of one idempotency key for a different operation."""

    status_code = 409
    default_code = "IDEMPOTENCY_CONFLICT"
    default_detail = "The idempotency key was already used with different input."


def create_job(
    owner,
    kind,
    title,
    parameters,
    uploaded_file,
    idempotency_key="",
    request_id="",
    source_job=None,
    workflow_run=None,
    workflow_step=None,
    reconcile_on_lease_loss=False,
):
    """Create an owned durable job and persist its validated input."""

    normalized_key = validate_idempotency_key(idempotency_key)
    digest = calculate_upload_sha256(uploaded_file)
    existing = find_idempotent_job(owner, kind, normalized_key)
    if existing:
        verify_idempotent_request(existing, digest, parameters)
        return existing, False
    job, created = persist_job(
        owner,
        kind,
        title,
        parameters,
        uploaded_file,
        digest,
        normalized_key,
        request_id,
        source_job,
        workflow_run,
        workflow_step,
        reconcile_on_lease_loss,
    )
    if not created:
        verify_idempotent_request(job, digest, parameters)
        return job, False
    record_event(job, "Job queued.")
    return job, True


def persist_job(
    owner,
    kind,
    title,
    parameters,
    upload,
    digest,
    key,
    request_id,
    source_job=None,
    workflow_run=None,
    workflow_step=None,
    reconcile_on_lease_loss=False,
):
    """Persist job metadata and its input artifact."""

    job = None
    try:
        with transaction.atomic():
            job = create_job_record(
                owner,
                kind,
                title,
                parameters,
                upload.name,
                digest,
                key,
                request_id,
                source_job,
                workflow_run,
                workflow_step,
                reconcile_on_lease_loss,
            )
            job.input_file.save(upload.name, upload, save=True)
        return job, True
    except IntegrityError:
        if not key:
            raise
        return Job.objects.get(owner=owner, kind=kind, idempotency_key=key), False
    except Exception:
        if job and job.input_file.name:
            job.input_file.storage.delete(job.input_file.name)
        raise


def create_job_record(
    owner,
    kind,
    title,
    parameters,
    input_name,
    digest,
    key,
    request_id,
    source_job=None,
    workflow_run=None,
    workflow_step=None,
    reconcile_on_lease_loss=False,
):
    """Create one job metadata row before its input artifact is committed."""

    return Job.objects.create(
        owner=owner,
        kind=kind,
        title=title,
        parameters=parameters,
        input_name=input_name,
        input_sha256=digest,
        idempotency_key=key,
        request_id=request_id,
        source_job=source_job,
        workflow_run=workflow_run,
        workflow_step=workflow_step,
        reconcile_on_lease_loss=bool(reconcile_on_lease_loss),
    )


def record_event(job, message, code="", details=None):
    """Append one sanitized immutable event for a job."""

    return JobEvent.objects.create(
        job=job,
        status=job.status,
        progress=job.progress,
        message=str(message)[:500],
        code=str(code)[:64],
        details=details or {},
    )


def calculate_upload_sha256(uploaded_file):
    """Calculate a streaming SHA-256 digest without retaining upload bytes."""

    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def validate_idempotency_key(value):
    """Validate an optional caller-provided idempotency key."""

    normalized = str(value or "").strip()
    if normalized and not IDEMPOTENCY_PATTERN.fullmatch(normalized):
        raise ValidationError({"idempotency_key": "Use 8-128 safe ASCII characters."})
    return normalized


def require_idempotency_key(value):
    """Validate the mandatory idempotency header used by public job starts."""

    normalized = validate_idempotency_key(value)
    if not normalized:
        raise ValidationError(
            {"idempotency_key": "An Idempotency-Key header is required."}
        )
    return normalized


def find_idempotent_job(owner, kind, key):
    """Return an existing idempotent request when one is available."""

    if not key:
        return None
    return Job.objects.filter(owner=owner, kind=kind, idempotency_key=key).first()


def verify_idempotent_request(job, digest, parameters):
    """Ensure an idempotency replay represents exactly the original request."""

    if job.input_sha256 != digest or job.parameters != parameters:
        raise IdempotencyConflict()
