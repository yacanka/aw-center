"""Feature-neutral state synchronization for durable multi-step workflows."""

import logging

from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError

from .handoffs import create_handoff_job
from .models import JobStatus
from .workflow_models import WorkflowRun, WorkflowStatus
from .workflow_state import mark_workflow_advance_failed, set_workflow_state

logger = logging.getLogger(__name__)


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
        logger.exception(
            "Workflow synchronization failed",
            extra={"workflow_id": str(job.workflow_run_id)},
        )
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
    elif job.status in {JobStatus.FAILED, JobStatus.RECONCILIATION_REQUIRED}:
        set_workflow_state(workflow, WorkflowStatus.FAILED, job.message, job.error_code)
    elif job.status == JobStatus.CANCELLED:
        set_workflow_state(workflow, WorkflowStatus.CANCELLED, "Workflow cancelled.", "")


def advance_succeeded_workflow(workflow, source_job):
    """Complete the run or queue its persisted, server-owned next transition."""

    if workflow.current_step >= workflow.total_steps:
        set_workflow_state(workflow, WorkflowStatus.SUCCEEDED, "Workflow completed.", "")
        return
    next_step = workflow_step(workflow, workflow.current_step + 1)
    transition = next_step.get("transition")
    if not isinstance(transition, dict) or transition.get(
        "target_kind"
    ) != next_step.get("kind"):
        raise ValidationError({"workflow": "The next workflow step is invalid."})
    target, _ = create_handoff_job(
        source_job,
        transition,
        workflow.request_id,
        workflow_run=workflow,
        workflow_step=next_step["sequence"],
    )
    attach_existing_target(workflow, target, next_step["sequence"])
    set_workflow_state(
        workflow,
        WorkflowStatus.QUEUED,
        f"{next_step['label']} queued.",
        "",
        next_step["sequence"],
        {"job_id": str(target.id)},
    )


def workflow_step(workflow, sequence):
    """Return one bounded step from the immutable definition selected at creation."""

    definition = workflow.definition if isinstance(workflow.definition, dict) else {}
    if definition.get("version") != 1 or not isinstance(definition.get("steps"), list):
        raise ValidationError({"workflow": "The workflow definition is invalid."})
    matches = [
        step
        for step in definition["steps"]
        if isinstance(step, dict) and step.get("sequence") == sequence
    ]
    if len(matches) != 1:
        raise ValidationError({"workflow": "The workflow definition is invalid."})
    step = matches[0]
    if (
        not isinstance(step.get("label"), str)
        or not step["label"]
        or len(step["label"]) > 160
    ):
        raise ValidationError({"workflow": "The workflow definition is invalid."})
    return step


def attach_existing_target(workflow, target, sequence):
    """Attach an idempotently replayed target when it is safe to do so."""

    if target.workflow_run_id not in {None, workflow.id}:
        raise RuntimeError("The target job belongs to another workflow.")
    if target.workflow_run_id is None:
        target.workflow_run = workflow
        target.workflow_step = sequence
        target.save(update_fields=["workflow_run", "workflow_step", "updated_at"])
