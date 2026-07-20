"""Recovery and user controls for durable workflows."""

from datetime import timedelta

from django.db.models import Prefetch
from django.utils import timezone

from .models import Job, JobStatus
from .services import request_cancellation
from .workflow_models import WorkflowRun, WorkflowStatus
from .workflow_services import synchronize_workflow_job
from .workflow_state import ACTIVE_WORKFLOW_STATUSES, set_workflow_state


def reconcile_active_workflows():
    """Heal workflows interrupted after a durable job state transition."""

    jobs = Job.objects.order_by("workflow_step", "attempt", "created_at")
    workflows = WorkflowRun.objects.filter(status__in=ACTIVE_WORKFLOW_STATUSES).prefetch_related(
        Prefetch("jobs", queryset=jobs)
    )[:100]
    for workflow in workflows:
        job = latest_current_job(workflow)
        if job and job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            synchronize_workflow_job(job)
        elif not job and workflow.created_at < timezone.now() - timedelta(seconds=30):
            set_workflow_state(
                workflow, WorkflowStatus.FAILED,
                "The first workflow step could not be queued.", "WORKFLOW_INITIALIZATION_FAILED",
            )


def latest_current_job(workflow):
    """Return the newest attempt for the workflow's current step."""

    candidates = [job for job in workflow.jobs.all() if job.workflow_step == workflow.current_step]
    return max(candidates, key=lambda job: (job.attempt, job.created_at)) if candidates else None


def cancel_workflow(workflow):
    """Request cancellation and preserve the worker-confirmed terminal state."""

    active_jobs = workflow.jobs.filter(
        status__in=[JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED]
    )
    for job in active_jobs:
        request_cancellation(job)
    workflow.refresh_from_db()
    if workflow.status in ACTIVE_WORKFLOW_STATUSES and not active_jobs.exists():
        set_workflow_state(workflow, WorkflowStatus.CANCELLED, "Workflow cancelled.", "")
    return workflow
