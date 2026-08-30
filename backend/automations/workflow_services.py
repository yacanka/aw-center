"""Creation boundary for static, server-owned durable automation workflows."""

import secrets

from django.db import IntegrityError

from jobs.persistence import (
    IdempotencyConflict,
    calculate_upload_sha256,
    create_job,
    require_idempotency_key,
)
from jobs.workflow_models import WorkflowRun
from jobs.workflow_state import record_workflow_event

from .recipes import (
    get_workflow_recipe,
    validate_workflow_parameters,
    workflow_definition,
)


def create_workflow_run(owner, recipe_id, parameters, upload, key="", request_id=""):
    """Create one workflow and its first durable job idempotently."""

    recipe = get_workflow_recipe(recipe_id)
    normalized = validate_workflow_parameters(recipe, parameters)
    normalized_key = require_idempotency_key(key)
    digest = calculate_upload_sha256(upload)
    existing = find_workflow_replay(owner, recipe.identifier, normalized_key)
    if existing:
        verify_workflow_replay(existing, digest, normalized)
        return existing, False
    workflow, created = persist_workflow(
        owner,
        recipe,
        normalized,
        upload.name,
        digest,
        normalized_key,
        request_id,
    )
    if not created:
        verify_workflow_replay(workflow, digest, normalized)
        return workflow, False
    create_first_workflow_job(workflow, recipe, upload)
    return workflow, True


def persist_workflow(owner, recipe, parameters, input_name, digest, key, request_id):
    """Persist recipe data while resolving concurrent idempotent requests."""

    try:
        workflow = WorkflowRun.objects.create(
            owner=owner,
            recipe=recipe.identifier,
            title=recipe.title,
            definition=workflow_definition(recipe),
            parameters=parameters,
            input_name=input_name[:180],
            input_sha256=digest,
            total_steps=len(recipe.steps),
            idempotency_key=key,
            request_id=request_id,
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
    """Create and audit the first job, removing incomplete metadata on failure."""

    step = recipe.steps[0]
    try:
        job, _ = create_job(
            workflow.owner,
            step.kind,
            f"{step.label}: {upload.name}"[:160],
            workflow.parameters,
            upload,
            f"workflow:{workflow.id}:step:1",
            workflow.request_id,
            workflow_run=workflow,
            workflow_step=1,
        )
    except Exception:
        workflow.delete()
        raise
    record_workflow_event(workflow, "Workflow queued.", {"job_id": str(job.id)})


def find_workflow_replay(owner, recipe, key):
    """Return an existing workflow for a caller-provided idempotency key."""

    if not key:
        return None
    return WorkflowRun.objects.filter(
        owner=owner, recipe=recipe, idempotency_key=key
    ).first()


def verify_workflow_replay(workflow, digest, parameters):
    """Reject reuse of one workflow key with different input or parameters."""

    same_digest = secrets.compare_digest(workflow.input_sha256, digest)
    if not same_digest or workflow.parameters != parameters:
        raise IdempotencyConflict()
