"""Generic, persisted workflow artifact transitions for the durable job kernel."""

import secrets
from pathlib import Path

from django.core.files import File
from rest_framework.exceptions import APIException, ValidationError

from awcenter.file_security import UploadPolicy, validate_uploaded_file

from .models import JobStatus
from .persistence import calculate_upload_sha256, create_job, record_event


class JobOutputIntegrityError(APIException):
    """Reject reuse when a stored output no longer matches its fingerprint."""

    status_code = 409
    default_code = "JOB_OUTPUT_INTEGRITY_FAILED"
    default_detail = "The completed output failed its integrity check and cannot be reused."


def create_handoff_job(
    source_job,
    definition,
    request_id="",
    workflow_run=None,
    workflow_step=None,
):
    """Verify and reuse output according to a server-persisted workflow definition."""

    normalized = validate_handoff_definition(definition)
    if not handoff_applies(normalized, source_job):
        raise ValidationError({"workflow": "The next workflow step is invalid."})
    with source_job.output_file.open("rb") as output:
        artifact = File(output, name=source_job.output_name)
        verify_artifact_integrity(artifact, source_job.output_sha256)
        validate_uploaded_file(artifact, upload_policy(normalized))
        artifact.seek(0)
        target_job, created = create_job(
            owner=source_job.owner,
            kind=normalized["target_kind"],
            title=f"{normalized['label']}: {source_job.output_name}"[:160],
            parameters=normalized["parameters"],
            uploaded_file=artifact,
            idempotency_key=(
                f"workflow:{workflow_run.id}:step:{workflow_step}"
                if workflow_run is not None
                else f"handoff:{source_job.id}:{normalized['id']}"
            ),
            request_id=request_id,
            source_job=source_job,
            workflow_run=workflow_run,
            workflow_step=workflow_step,
        )
    if created:
        record_handoff_events(source_job, target_job, normalized)
    return target_job, created


def validate_handoff_definition(definition):
    """Accept only the bounded data shape persisted by automation recipe creation."""

    if not isinstance(definition, dict):
        raise ValidationError({"workflow": "The next workflow step is invalid."})
    normalized = {
        "id": bounded_identifier(definition.get("id")),
        "source_kind": bounded_identifier(definition.get("source_kind")),
        "target_kind": bounded_identifier(definition.get("target_kind")),
        "label": str(definition.get("label") or "")[:160],
        "extensions": normalized_extensions(definition.get("extensions")),
        "limit_setting": bounded_identifier(definition.get("limit_setting")),
        "default_limit": definition.get("default_limit"),
        "parameters": definition.get("parameters"),
    }
    valid = (
        all(normalized[key] for key in ("id", "source_kind", "target_kind", "label"))
        and normalized["extensions"]
        and normalized["limit_setting"].startswith("AWCENTER_")
        and isinstance(normalized["parameters"], dict)
        and isinstance(normalized["default_limit"], int)
        and not isinstance(normalized["default_limit"], bool)
        and 0 < normalized["default_limit"] <= 600 * 1024 * 1024
    )
    if not valid:
        raise ValidationError({"workflow": "The next workflow step is invalid."})
    return normalized


def bounded_identifier(value):
    """Normalize a non-secret persisted identifier without accepting path syntax."""

    normalized = str(value or "")
    if not normalized or len(normalized) > 128:
        return ""
    if not all(character.isalnum() or character in "._-" for character in normalized):
        return ""
    return normalized


def normalized_extensions(value):
    """Return a bounded set of lowercase dot-prefixed extensions."""

    if not isinstance(value, list) or not 1 <= len(value) <= 10:
        return frozenset()
    extensions = frozenset(str(item).lower() for item in value)
    if any(
        not item.startswith(".")
        or len(item) > 12
        or not item[1:].isalnum()
        for item in extensions
    ):
        return frozenset()
    return extensions


def upload_policy(definition):
    """Rebuild only the upload policy data fixed by the selected server recipe."""

    return UploadPolicy(
        definition["extensions"],
        definition["limit_setting"],
        definition["default_limit"],
    )


def handoff_applies(definition, job):
    """Return whether immutable output metadata satisfies a workflow transition."""

    return (
        job.status == JobStatus.SUCCEEDED
        and bool(job.output_file)
        and bool(job.output_sha256)
        and job.kind == definition["source_kind"]
        and Path(job.output_name).suffix.lower() in definition["extensions"]
    )


def verify_artifact_integrity(artifact, expected_digest):
    """Compare stored artifact bytes with the worker-generated fingerprint."""

    actual_digest = calculate_upload_sha256(artifact)
    if not secrets.compare_digest(actual_digest, expected_digest):
        raise JobOutputIntegrityError()


def record_handoff_events(source_job, target_job, definition):
    """Append sanitized provenance events to both sides of an internal transition."""

    details = {"transition_id": definition["id"], "target_job_id": str(target_job.id)}
    record_event(source_job, f"Output advanced to {definition['label']}.", details=details)
    record_event(
        target_job,
        "Input reused from a verified completed workflow step.",
        details={"source_job_id": str(source_job.id), "transition_id": definition["id"]},
    )
