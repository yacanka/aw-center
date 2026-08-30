"""Feature-state fencing for ECR external-write jobs."""

from django.db import transaction
from django.utils import timezone

from jobs.contracts import JobExecutionFailure
from jobs.execution import current_execution_lease, lock_active_execution

from .ecr_access import PUBLISHER, require_ecr_role
from .ecr_services import record_ecr_event
from .models import EcrWorkflow, EcrWorkflowStatus


def validate_ecr_publication_fence(job):
    """Recheck the active job lease, workflow reservation, and project roles."""

    with transaction.atomic():
        return locked_active_workflow(job, allow_completed=True)


def confirm_parent(job, issue_key):
    with transaction.atomic():
        workflow = locked_active_workflow(job)
        state = normalized_state(workflow)
        state["parent_confirmed"] = True
        state["uncertain_operation"] = ""
        workflow.jira_issue_key = issue_key
        workflow.publication_state = state
        workflow.save(
            update_fields=["jira_issue_key", "publication_state", "updated_at"]
        )
        return workflow


def confirm_attachment(job):
    with transaction.atomic():
        workflow = locked_active_workflow(job)
        state = normalized_state(workflow)
        state["attachment_confirmed"] = True
        state["uncertain_operation"] = ""
        workflow.publication_state = state
        workflow.save(update_fields=["publication_state", "updated_at"])
        return workflow


def confirm_subtask(job, index, issue_key):
    with transaction.atomic():
        workflow = locked_active_workflow(job)
        state = normalized_state(workflow)
        keys = dict(state["subtask_keys"])
        keys[str(index)] = issue_key
        state["subtask_keys"] = keys
        state["uncertain_operation"] = ""
        workflow.publication_state = state
        workflow.save(update_fields=["publication_state", "updated_at"])
        return workflow


def fail_ecr_publication(job, code, message, *, uncertain_operation=""):
    """Persist one bounded terminal feature outcome while the lease is current."""

    with transaction.atomic():
        workflow = locked_active_workflow(job, require_role=False)
        if uncertain_operation:
            state = normalized_state(workflow)
            state["uncertain_operation"] = str(uncertain_operation)[:64]
            workflow.publication_state = state
            workflow.status = EcrWorkflowStatus.RECONCILIATION_REQUIRED
            event_type = "reconciliation_required"
        else:
            workflow.status = EcrWorkflowStatus.FAILED
            event_type = "publication_failed"
        workflow.last_error_code = str(code)[:64]
        workflow.last_error_message = str(message)[:500]
        workflow.version += 1
        workflow.save()
        record_ecr_event(
            workflow,
            job.owner,
            event_type,
            code=code,
            details={"job_id": str(job.id)},
        )
        return workflow


def complete_ecr_publication(job):
    with transaction.atomic():
        workflow = locked_active_workflow(job)
        state = normalized_state(workflow)
        if not publication_complete(workflow, state):
            raise publication_fence_lost()
        state["uncertain_operation"] = ""
        workflow.publication_state = state
        workflow.status = EcrWorkflowStatus.PUBLISHED
        workflow.published_at = timezone.now()
        workflow.last_error_code = ""
        workflow.last_error_message = ""
        workflow.version += 1
        workflow.save()
        record_ecr_event(
            workflow,
            job.owner,
            "published",
            details={"job_id": str(job.id), "jira_issue_key": workflow.jira_issue_key},
        )
        return workflow


def locked_active_workflow(job, *, allow_completed=False, require_role=True):
    lease = current_execution_lease(job.id)
    active_job = lock_active_execution(lease, allow_cancel_requested=True)
    try:
        workflow = (
            EcrWorkflow.objects.select_for_update()
            .prefetch_related("projects")
            .get(pk=active_job.parameters.get("workflow_id"))
        )
    except (EcrWorkflow.DoesNotExist, TypeError, ValueError) as error:
        raise publication_fence_lost() from error
    active = (
        workflow.status == EcrWorkflowStatus.PUBLISHING
        and workflow.version == active_job.parameters.get("fence_version")
    )
    completed = (
        allow_completed
        and workflow.status == EcrWorkflowStatus.PUBLISHED
        and bool(workflow.jira_issue_key)
    )
    if workflow.publication_job_id != active_job.id or not (active or completed):
        raise publication_fence_lost()
    if active_job.owner_id != workflow.owner_id:
        raise publication_fence_lost()
    project_slugs = sorted(workflow.projects.values_list("slug", flat=True))
    if project_slugs != active_job.parameters.get("project_slugs"):
        raise publication_fence_lost()
    if require_role:
        require_ecr_role(active_job.owner, workflow, PUBLISHER)
    return workflow


def normalized_state(workflow):
    state = dict(workflow.publication_state or {})
    state["parent_confirmed"] = bool(state.get("parent_confirmed"))
    state["attachment_confirmed"] = bool(state.get("attachment_confirmed"))
    state["subtask_keys"] = (
        dict(state.get("subtask_keys"))
        if isinstance(state.get("subtask_keys"), dict)
        else {}
    )
    state["uncertain_operation"] = str(state.get("uncertain_operation") or "")[:64]
    return state


def publication_complete(workflow, state):
    return bool(
        workflow.jira_issue_key
        and state["parent_confirmed"]
        and state["attachment_confirmed"]
        and len(state["subtask_keys"]) == len(workflow.selected_subtasks or ())
    )


def publication_fence_lost():
    return JobExecutionFailure(
        "The ECR publication reservation is no longer valid.",
        "ECR_PUBLICATION_FENCE_LOST",
        retryable=False,
    )
