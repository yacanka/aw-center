"""Idempotent state machine for durable multi-step workflows."""

import logging
import secrets

from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException

from .handoffs import create_handoff_job
from .models import Job, JobStatus
from .services import (
    IdempotencyConflict,
    calculate_upload_sha256,
    create_job,
    validate_idempotency_key,
)
from .workflow_models import WorkflowRun, WorkflowStatus
from .workflow_recipes import get_workflow_recipe, validate_workflow_parameters
from .workflow_state import (
    mark_workflow_advance_failed,
    record_workflow_event,
    set_workflow_state,
)

logger = logging.getLogger(__name__)


def create_workflow_run(owner, recipe_id, parameters, upload, key="", request_id=""):
    """Create one workflow and its first durable job idempotently."""

    recipe = get_workflow_recipe(recipe_id)
    normalized = validate_workflow_parameters(recipe, parameters)
    normalized_key = validate_idempotency_key(key)
    digest = calculate_upload_sha256(upload)
    existing = find_workflow_replay(owner, recipe.identifier, normalized_key)
    if existing:
        verify_workflow_replay(existing, digest, normalized)
        return existing, False
    workflow, created = persist_workflow(
        owner, recipe, normalized, upload.name, digest, normalized_key, request_id
    )
    if not created:
        verify_workflow_replay(workflow, digest, normalized)
        return workflow, False
    create_first_workflow_job(workflow, recipe, upload)
    return workflow, True


def persist_workflow(owner, recipe, parameters, input_name, digest, key, request_id):
    """Persist workflow metadata while resolving concurrent idempotent requests."""

    try:
        workflow = WorkflowRun.objects.create(
            owner=owner, recipe=recipe.identifier, title=recipe.title,
            parameters=parameters, input_name=input_name[:180], input_sha256=digest,
            total_steps=len(recipe.steps), idempotency_key=key, request_id=request_id,
            message="Workflow queued.",
        )
        return workflow, True
    except IntegrityError:
        if not key:
            raise
        workflow = WorkflowRun.objects.filter(
            owner=owner, recipe=recipe.identifier, idempotency_key=key
        ).first()
        if not workflow:
            raise
        return workflow, False


def create_first_workflow_job(workflow, recipe, upload):
    """Create and audit the first job, removing incomplete workflow metadata on failure."""

    step = recipe.steps[0]
    try:
        job, _ = create_job(
            workflow.owner, step.kind, f"{step.label}: {upload.name}"[:160],
            workflow.parameters, upload, f"workflow:{workflow.id}:step:1",
            workflow.request_id, workflow_run=workflow, workflow_step=1,
        )
    except Exception:
        workflow.delete()
        raise
    record_workflow_event(workflow, "Workflow queued.", {"job_id": str(job.id)})


def find_workflow_replay(owner, recipe, key):
    """Return an existing workflow for a caller-provided idempotency key."""

    if not key:
        return None
    return WorkflowRun.objects.filter(owner=owner, recipe=recipe, idempotency_key=key).first()


def verify_workflow_replay(workflow, digest, parameters):
    """Reject reuse of one workflow key with different input or parameters."""

    same_digest = secrets.compare_digest(workflow.input_sha256, digest)
    if not same_digest or workflow.parameters != parameters:
        raise IdempotencyConflict()


def synchronize_workflow_job(job):
    """Advance or terminate the attached workflow from one durable job state."""

    if not job.workflow_run_id:
        return
    try:
        synchronize_locked_workflow(job)
    except APIException as error:
        logger.warning(
            "Workflow transition rejected",
            extra={"workflow_id": str(job.workflow_run_id), "code": error.default_code},
        )
        mark_workflow_advance_failed(job.workflow_run_id)
    except Exception:
        logger.exception("Workflow synchronization failed", extra={"workflow_id": str(job.workflow_run_id)})
        mark_workflow_advance_failed(job.workflow_run_id)


def synchronize_locked_workflow(job):
    """Apply one job state under the workflow row lock."""

    with transaction.atomic():
        workflow = WorkflowRun.objects.select_for_update().get(pk=job.workflow_run_id)
        if job.workflow_step != workflow.current_step:
            return
        if job.status == JobStatus.SUCCEEDED:
            advance_succeeded_workflow(workflow, job)
            return
        synchronize_non_success_state(workflow, job)


def synchronize_non_success_state(workflow, job):
    """Map a non-success job state to its workflow representation."""

    if job.status == JobStatus.QUEUED:
        set_workflow_state(workflow, WorkflowStatus.QUEUED, "Step queued.", "")
    elif job.status == JobStatus.RUNNING:
        set_workflow_state(workflow, WorkflowStatus.RUNNING, job.message, "")
    elif job.status == JobStatus.CANCEL_REQUESTED:
        set_workflow_state(
            workflow, WorkflowStatus.CANCEL_REQUESTED, "Cancellation requested.", ""
        )
    elif job.status == JobStatus.FAILED:
        set_workflow_state(workflow, WorkflowStatus.FAILED, job.message, job.error_code)
    elif job.status == JobStatus.CANCELLED:
        set_workflow_state(workflow, WorkflowStatus.CANCELLED, "Workflow cancelled.", "")


def advance_succeeded_workflow(workflow, source_job):
    """Complete the run or queue its next allowlisted artifact handoff."""

    if workflow.current_step >= workflow.total_steps:
        set_workflow_state(workflow, WorkflowStatus.SUCCEEDED, "Workflow completed.", "")
        return
    recipe = get_workflow_recipe(workflow.recipe)
    next_step = recipe.steps[workflow.current_step]
    target, _ = create_handoff_job(
        source_job, next_step.handoff_id, workflow.request_id,
        workflow_run=workflow, workflow_step=next_step.sequence,
    )
    attach_existing_target(workflow, target, next_step.sequence)
    set_workflow_state(
        workflow, WorkflowStatus.QUEUED, f"{next_step.label} queued.", "",
        next_step.sequence, {"job_id": str(target.id)},
    )


def attach_existing_target(workflow, target, sequence):
    """Attach an idempotently replayed target when it is safe to do so."""

    if target.workflow_run_id not in {None, workflow.id}:
        raise RuntimeError("The target job belongs to another workflow.")
    if target.workflow_run_id is None:
        target.workflow_run = workflow
        target.workflow_step = sequence
        target.save(update_fields=["workflow_run", "workflow_step", "updated_at"])
