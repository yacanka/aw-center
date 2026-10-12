"""Fenced state transitions for durable JIRA draft publication jobs."""

from django.db import transaction
from django.utils import timezone

from jobs.contracts import JobExecutionFailure
from jobs.models import JobStatus

from .access_policy import PUBLISHER, require_resource_role
from .issue_draft_models import JiraIssueDraft, JiraIssueDraftStatus
from .issue_draft_services import record_event


def validate_publication_fence(job):
    """Recheck job ownership, project roles, and the reserved draft version."""

    with transaction.atomic():
        try:
            draft = (
                JiraIssueDraft.objects.select_for_update()
                .prefetch_related("projects", "assigned_users")
                .get(pk=job.parameters.get("draft_id"))
            )
        except (JiraIssueDraft.DoesNotExist, TypeError, ValueError) as error:
            raise fence_lost() from error
        valid_active_fence = (
            draft.status == JiraIssueDraftStatus.PUBLISHING
            and draft.version == job.parameters.get("fence_version")
        )
        completed_by_job = (
            draft.status == JiraIssueDraftStatus.PUBLISHED
            and bool(draft.jira_issue_key)
        )
        if draft.publication_job_id != job.id or not (
            valid_active_fence or completed_by_job
        ):
            raise fence_lost()
        require_resource_role(job.owner, draft, PUBLISHER)
        project_ids = sorted(draft.projects.values_list("pk", flat=True))
        if project_ids != job.parameters.get("project_ids"):
            raise fence_lost()
        return draft


def complete_publication(job, issue_key, *, reconciled=False):
    with transaction.atomic():
        draft = locked_job_draft(job)
        draft.status = JiraIssueDraftStatus.PUBLISHED
        draft.jira_issue_key = issue_key
        draft.published_by = job.owner
        draft.published_at = timezone.now()
        draft.last_error_code = ""
        draft.last_error_message = ""
        draft.version += 1
        draft.save()
        record_event(
            draft,
            job.owner,
            "publication_reconciled" if reconciled else "published",
            {"jira_issue_key": issue_key, "job_id": str(job.id)},
        )
        return draft


def fail_publication(job, code, message, *, reconciliation_required=False):
    """Persist only bounded failure metadata if this job still owns the fence."""

    with transaction.atomic():
        draft = locked_job_draft(job)
        draft.status = (
            JiraIssueDraftStatus.RECONCILIATION_REQUIRED
            if reconciliation_required
            else JiraIssueDraftStatus.FAILED
        )
        draft.last_error_code = str(code)[:64]
        draft.last_error_message = str(message)[:500]
        draft.version += 1
        draft.save()
        record_event(
            draft,
            job.owner,
            "reconciliation_required" if reconciliation_required else "publication_failed",
            {"code": draft.last_error_code, "job_id": str(job.id)},
        )
        return draft


def project_publication_job_terminal(job):
    """Repair draft state when the parent job terminates outside the executor."""

    if job.kind != "dcc.publish_jira_draft" or job.status not in {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.RECONCILIATION_REQUIRED,
    }:
        return
    with transaction.atomic():
        draft = (
            JiraIssueDraft.objects.select_for_update()
            .filter(publication_job_id=job.id)
            .first()
        )
        if draft is None:
            return
        target, event_type = projected_terminal_state(draft, job)
        if target is None or draft.status == target:
            return
        draft.status = target
        draft.last_error_code = str(job.error_code or job.status)[:64]
        draft.last_error_message = str(job.message or "Publication job ended.")[:500]
        draft.version += 1
        draft.save()
        record_event(
            draft,
            job.owner,
            event_type,
            {"code": draft.last_error_code, "job_id": str(job.id)},
        )


def projected_terminal_state(draft, job):
    """Return the safe draft projection for one terminal job state."""

    if job.status == JobStatus.SUCCEEDED:
        # The executor confirms the external key before artifact publication.
        # A success projection is therefore already PUBLISHED; anything else
        # indicates a lost fence and must not invent provider state.
        return (None, "") if draft.status == JiraIssueDraftStatus.PUBLISHED else (
            JiraIssueDraftStatus.RECONCILIATION_REQUIRED,
            "reconciliation_required",
        )
    if job.status == JobStatus.RECONCILIATION_REQUIRED or (
        draft.status == JiraIssueDraftStatus.PUBLISHED
    ):
        return JiraIssueDraftStatus.RECONCILIATION_REQUIRED, "reconciliation_required"
    return JiraIssueDraftStatus.FAILED, "publication_failed"


def locked_job_draft(job):
    try:
        draft = (
            JiraIssueDraft.objects.select_for_update()
            .prefetch_related("projects", "assigned_users")
            .get(pk=job.parameters.get("draft_id"))
        )
    except (JiraIssueDraft.DoesNotExist, TypeError, ValueError) as error:
        raise fence_lost() from error
    valid = (
        draft.publication_job_id == job.id
        and draft.status == JiraIssueDraftStatus.PUBLISHING
        and draft.version == job.parameters.get("fence_version")
    )
    if not valid:
        raise fence_lost()
    return draft


def fence_lost():
    return JobExecutionFailure(
        "The JIRA draft publication reservation is no longer valid.",
        "JIRA_DRAFT_FENCE_LOST",
        retryable=False,
    )
