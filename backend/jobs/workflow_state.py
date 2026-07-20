"""Shared persistence helpers for workflow state and audit events."""

from django.db import transaction
from django.utils import timezone

from .workflow_models import WorkflowRun, WorkflowRunEvent, WorkflowStatus

ACTIVE_WORKFLOW_STATUSES = {
    WorkflowStatus.QUEUED, WorkflowStatus.RUNNING, WorkflowStatus.CANCEL_REQUESTED
}


def set_workflow_state(workflow, status, message, code="", step=None, details=None):
    """Persist one bounded state transition and its immutable audit event."""

    next_step = step or workflow.current_step
    next_values = (status, str(message)[:500], str(code)[:64], next_step)
    current_values = (
        workflow.status, workflow.message, workflow.error_code, workflow.current_step
    )
    if current_values == next_values:
        return
    workflow.status, workflow.message, workflow.error_code, workflow.current_step = next_values
    workflow.completed_at = timezone.now() if status not in ACTIVE_WORKFLOW_STATUSES else None
    workflow.save()
    record_workflow_event(workflow, workflow.message, details, workflow.error_code)


def record_workflow_event(workflow, message, details=None, code=""):
    """Append one sanitized immutable workflow event."""

    return WorkflowRunEvent.objects.create(
        workflow=workflow, status=workflow.status, step=workflow.current_step,
        message=str(message)[:500], code=str(code)[:64], details=details or {},
    )


def mark_workflow_advance_failed(workflow_id):
    """Fail one active workflow without changing its successfully completed job."""

    with transaction.atomic():
        workflow = WorkflowRun.objects.select_for_update().get(pk=workflow_id)
        if workflow.status in ACTIVE_WORKFLOW_STATUSES:
            set_workflow_state(
                workflow, WorkflowStatus.FAILED,
                "The next workflow step could not be queued.", "WORKFLOW_ADVANCE_FAILED",
            )
