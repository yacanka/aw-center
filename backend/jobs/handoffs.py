"""Allowlisted server-side handoffs between compatible durable jobs."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from django.core.files import File
from rest_framework.exceptions import APIException, NotFound

from awcenter.file_security import UploadPolicy, WORD_DOCUMENT_POLICY, validate_uploaded_file
from word.analysis_contracts import ANALYSIS_CHECKS

from .models import JobStatus
from .services import calculate_upload_sha256, create_job, record_event


class JobOutputIntegrityError(APIException):
    """Reject reuse when a stored output no longer matches its fingerprint."""

    status_code = 409
    default_code = "JOB_OUTPUT_INTEGRITY_FAILED"
    default_detail = "The completed output failed its integrity check and cannot be reused."


@dataclass(frozen=True)
class JobHandoffDefinition:
    """Describe one safe source-to-target job transition."""

    identifier: str
    source_kind: str
    target_kind: str
    label: str
    description: str
    extensions: frozenset[str]
    upload_policy: UploadPolicy
    parameters: Callable[[], dict]


def analysis_parameters():
    """Return a fresh default explainable-analysis checklist."""

    return {"check_ids": list(ANALYSIS_CHECKS)}


ANALYZE_TRANSLATION = JobHandoffDefinition(
    identifier="analyze-translated-document",
    source_kind="word.translate",
    target_kind="word.analyze",
    label="Analyze translated document",
    description="Reuse this private Word output for explainable compliance checks.",
    extensions=frozenset({".docx"}),
    upload_policy=WORD_DOCUMENT_POLICY,
    parameters=analysis_parameters,
)
ANALYZE_OUTLOOK_ATTACHMENT = JobHandoffDefinition(
    identifier="analyze-outlook-word-attachment",
    source_kind="outlook.extract_word_attachment",
    target_kind="word.analyze",
    label="Analyze extracted Word attachment",
    description="Run explainable checks on the verified private Outlook attachment.",
    extensions=frozenset({".docx"}),
    upload_policy=WORD_DOCUMENT_POLICY,
    parameters=analysis_parameters,
)
HANDOFFS = {
    definition.identifier: definition
    for definition in (ANALYZE_TRANSLATION, ANALYZE_OUTLOOK_ATTACHMENT)
}


def available_handoffs(job):
    """Return safe next actions available for one completed job."""

    return [handoff_payload(item) for item in HANDOFFS.values() if handoff_applies(item, job)]


def handoff_payload(definition):
    """Serialize a handoff definition without internal implementation data."""

    return {
        "id": definition.identifier,
        "label": definition.label,
        "description": definition.description,
        "target_kind": definition.target_kind,
    }


def handoff_applies(definition, job):
    """Return whether immutable output metadata satisfies a handoff contract."""

    extension = Path(job.output_name).suffix.lower()
    return (
        job.status == JobStatus.SUCCEEDED
        and bool(job.output_file)
        and bool(job.output_sha256)
        and job.kind == definition.source_kind
        and extension in definition.extensions
    )


def create_handoff_job(
    source_job, handoff_id, request_id="", workflow_run=None, workflow_step=None
):
    """Verify and reuse one owned output as a new durable job input."""

    definition = HANDOFFS.get(handoff_id)
    if not definition or not handoff_applies(definition, source_job):
        raise NotFound("This next action is not available for the selected job.")
    with source_job.output_file.open("rb") as output:
        artifact = File(output, name=source_job.output_name)
        verify_artifact_integrity(artifact, source_job.output_sha256)
        validate_uploaded_file(artifact, definition.upload_policy)
        artifact.seek(0)
        target_job, created = create_target_job(
            source_job, definition, artifact, request_id, workflow_run, workflow_step
        )
    if created:
        record_handoff_events(source_job, target_job, definition)
    return target_job, created


def verify_artifact_integrity(artifact, expected_digest):
    """Compare stored artifact bytes with the worker-generated fingerprint."""

    actual_digest = calculate_upload_sha256(artifact)
    if not secrets.compare_digest(actual_digest, expected_digest):
        raise JobOutputIntegrityError()


def create_target_job(
    source_job, definition, artifact, request_id, workflow_run=None, workflow_step=None
):
    """Create an idempotent target job from a verified source artifact."""

    return create_job(
        owner=source_job.owner,
        kind=definition.target_kind,
        title=f"{definition.label}: {source_job.output_name}"[:160],
        parameters=definition.parameters(),
        uploaded_file=artifact,
        idempotency_key=f"handoff:{source_job.id}:{definition.identifier}",
        request_id=request_id,
        source_job=source_job,
        workflow_run=workflow_run,
        workflow_step=workflow_step,
    )


def record_handoff_events(source_job, target_job, definition):
    """Append sanitized provenance events to both sides of a handoff."""

    details = {"handoff_id": definition.identifier, "target_job_id": str(target_job.id)}
    record_event(source_job, f"Output handed off to {definition.label}.", details=details)
    record_event(
        target_job,
        "Input reused from a verified completed job.",
        details={"source_job_id": str(source_job.id), "handoff_id": definition.identifier},
    )
