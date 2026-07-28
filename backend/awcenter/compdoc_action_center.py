"""User-specific Compliance Document attention signals."""

from datetime import datetime, time, timedelta

from django.apps import apps
from django.utils import timezone

from common.compdoc_lifecycle_models import CompDocReviewTask
from projects.registry import PROJECT_DEFINITIONS


def compdoc_attention_items(user, item_factory, limit):
    """Return bounded owner and review items across visible projects."""

    return [
        *owner_items(user, item_factory, limit),
        *review_items(user, item_factory, limit),
    ]


def owner_items(user, item_factory, limit):
    """Return due owner actions from projects visible to the current user."""

    items = []
    for slug in PROJECT_DEFINITIONS:
        model = apps.get_model(slug, "CompDoc")
        if not user.has_perm(f"{slug}.view_compdoc"):
            continue
        documents = model.objects.filter(
            owner=user,
            is_archived=False,
            next_action_due_date__isnull=False,
            next_action_due_date__lte=timezone.localdate() + timedelta(days=7),
        ).only("id", "name", "next_action_due_date").order_by("next_action_due_date")[:limit]
        items.extend(_owner_item(item_factory, slug, document) for document in documents)
    return items


def review_items(user, item_factory, limit):
    """Return due pending reviews assigned to the current user."""

    boundary = timezone.localdate() + timedelta(days=7)
    tasks = CompDocReviewTask.objects.filter(
        assignee=user,
        status=CompDocReviewTask.Status.PENDING,
        due_date__isnull=False,
        due_date__lte=boundary,
    ).order_by("due_date")[:limit]
    return [
        _review_item(item_factory, task)
        for task in tasks
        if user.has_perm(f"{task.project_slug}.view_compdoc")
    ]


def _owner_item(item_factory, slug, document):
    overdue = document.next_action_due_date < timezone.localdate()
    return item_factory(
        identifier=f"compdoc-owner:{slug}:{document.pk}",
        kind="compdoc_owner",
        severity="critical" if overdue else "warning",
        title=f"Document action: {document.name}",
        detail="Owner action is overdue." if overdue else "Owner action is due within seven days.",
        guidance="Review ownership, deadline, and the next lifecycle action.",
        action_label="Open document",
        action_path=f"/compdocs/{slug}?document={document.pk}",
        occurred_at=timezone.now(),
        due_at=_due_datetime(document.next_action_due_date),
    )


def _review_item(item_factory, task):
    overdue = task.due_date < timezone.localdate()
    return item_factory(
        identifier=f"compdoc-review:{task.pk}",
        kind=f"compdoc_{task.kind}",
        severity="critical" if overdue else "warning",
        title=f"{task.get_kind_display()} decision required",
        detail="Assigned decision is overdue." if overdue else "Assigned decision is due soon.",
        guidance="Open the document, review its evidence, and record a signed decision.",
        action_label="Open review",
        action_path=f"/compdocs/{task.project_slug}?document={task.document_id}",
        occurred_at=task.created_at,
        due_at=_due_datetime(task.due_date),
    )


def _due_datetime(value):
    return timezone.make_aware(datetime.combine(value, time.min))
