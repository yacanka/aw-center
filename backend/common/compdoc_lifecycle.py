"""Transactional lifecycle operations for project compliance documents."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.compdoc_lifecycle_models import CompDocReviewTask, CompDocWorkflowEvent
from common.compdoc_versions import CompDocVersionConflict, latest_history_id
from common.compdoc_workflow import WORKFLOW_STATUSES


@transaction.atomic
def transition_document(model, document, data, user, source=CompDocWorkflowEvent.Source.MANUAL):
    """Append an audited free-form transition and synchronize projections."""

    locked = model.objects.select_for_update().get(pk=document.pk)
    _require_version(model, locked.pk, data["source_history_id"])
    status = data["status"]
    if status not in WORKFLOW_STATUSES:
        raise ValidationError({"status": "Select a supported workflow status."})
    sequence = (
        CompDocWorkflowEvent.objects.filter(
            project_slug=model._meta.app_label, document_id=locked.pk
        ).count() + 1
    )
    event = CompDocWorkflowEvent.objects.create(
        project_slug=model._meta.app_label,
        document_id=locked.pk,
        sequence=sequence,
        previous_status=locked.status,
        status=status,
        effective_date=data["effective_date"],
        next_action_due_date=data.get("next_action_due_date"),
        reason=data["reason"],
        source=source,
        actor=user,
        actor_username=user.get_username(),
    )
    flow = list(locked.status_flow or [])
    flow.append({"status": status, "date": event.effective_date.strftime("%d.%m.%Y"),
                 "note": event.reason})
    locked.status_flow = flow
    locked.next_action_due_date = event.next_action_due_date
    locked._history_user = user
    locked._change_reason = event.reason[:100]
    locked.save(update_fields=["status_flow", "next_action_due_date"])
    return locked, event


@transaction.atomic
def update_work(model, document, data, user):
    """Update user/group ownership with optimistic concurrency."""

    locked = model.objects.select_for_update().get(pk=document.pk)
    _require_version(model, locked.pk, data["source_history_id"])
    changed_fields = [
        field
        for field in ("owner", "owner_group", "next_action_due_date")
        if field in data
    ]
    for field in changed_fields:
        setattr(locked, field, data[field])
    locked._history_user = user
    locked._change_reason = data["reason"][:100]
    locked.save(update_fields=changed_fields)
    return locked


@transaction.atomic
def set_archive_state(model, document, archived, data, user):
    """Archive or restore without destroying document evidence."""

    locked = model.objects.select_for_update().get(pk=document.pk)
    _require_version(model, locked.pk, data["source_history_id"])
    locked.is_archived = archived
    locked.archived_at = timezone.now() if archived else None
    locked.archived_by = user if archived else None
    locked.archive_reason = data["reason"] if archived else ""
    locked._history_user = user
    locked._change_reason = data["reason"][:100]
    locked.save(update_fields=["is_archived", "archived_at", "archived_by", "archive_reason"])
    return locked


def decide_review(task, status, note, user):
    """Record an assigned user's review decision without changing lifecycle state."""

    if task.assignee_id != user.pk and not user.has_perm("common.manage_compdoc_workflow"):
        raise PermissionDenied("Only the assignee may decide this task.")
    if task.status != CompDocReviewTask.Status.PENDING:
        raise ValidationError({"status": "This task is no longer pending."})
    task.status = status
    task.decision_note = note
    task.decided_by = user
    task.decided_by_username = user.get_username()
    task.decided_at = timezone.now()
    task.save()
    return task


def cancel_review(task, note, user):
    """Cancel a pending task without changing document lifecycle state."""

    if task.status != CompDocReviewTask.Status.PENDING:
        raise ValidationError({"status": "This task is no longer pending."})
    task.status = CompDocReviewTask.Status.CANCELLED
    task.decision_note = note
    task.decided_by = user
    task.decided_by_username = user.get_username()
    task.decided_at = timezone.now()
    task.save()
    return task


def _require_version(model, document_id, expected):
    if latest_history_id(model, document_id) != expected:
        raise CompDocVersionConflict()
