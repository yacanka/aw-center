"""Compliance-owned Action Center projections."""

from datetime import datetime, time, timedelta

from django.db.models import F
from django.utils import timezone

from orgs.access_policy import has_project_role
from orgs.models import ProjectRoleAssignment

from .models import ComplianceDocument, NotificationLog, ReviewTask, TrackingProfile


def compliance_attention_items(user, item_factory, limit):
    return [
        *owner_items(user, item_factory, limit),
        *review_items(user, item_factory, limit),
        *tracking_items(user, item_factory, limit),
    ]


def owner_items(user, item_factory, limit):
    boundary = timezone.localdate() + timedelta(days=7)
    documents = ComplianceDocument.objects.filter(
        owner=user,
        project__enabled=True,
        is_archived=False,
        next_action_due_date__isnull=False,
        next_action_due_date__lte=boundary,
    ).select_related("project").order_by("next_action_due_date")[:limit]
    return [
        _owner_item(item_factory, document)
        for document in documents
        if has_project_role(
            user,
            document.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.VIEWER,
        )
    ]


def review_items(user, item_factory, limit):
    boundary = timezone.localdate() + timedelta(days=7)
    tasks = ReviewTask.objects.filter(
        assignee=user,
        status=ReviewTask.Status.PENDING,
        due_date__isnull=False,
        due_date__lte=boundary,
        document__project__enabled=True,
        document__is_archived=False,
        source_version=F("document__version"),
    ).select_related("document__project").order_by("due_date")[:limit]
    return [
        _review_item(item_factory, task)
        for task in tasks
        if has_project_role(
            user,
            task.document.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.VIEWER,
        )
    ]


def tracking_items(user, item_factory, limit):
    revisions = TrackingProfile.objects.filter(
        document__owner=user,
        document__project__enabled=True,
        document__is_archived=False,
        docproof_status="revision_available",
    ).select_related("document__project").order_by("docproof_checked_at")[:limit]
    failures = NotificationLog.objects.filter(
        profile__document__owner=user,
        profile__document__project__enabled=True,
        profile__document__is_archived=False,
        status=NotificationLog.Status.FAILED,
    ).select_related("profile__document__project").order_by("next_attempt_at")[:limit]
    items = []
    for profile in revisions:
        if has_project_role(
            user,
            profile.document.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.VIEWER,
        ):
            items.append(_revision_item(item_factory, profile))
    for log in failures:
        if has_project_role(
            user,
            log.profile.document.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.VIEWER,
        ):
            items.append(_notification_failure_item(item_factory, log))
    return items


def _owner_item(item_factory, document):
    overdue = document.next_action_due_date < timezone.localdate()
    return item_factory(
        identifier=f"compliance-owner:{document.pk}",
        kind="compliance_owner",
        severity="critical" if overdue else "warning",
        title=f"Document action: {document.name}",
        detail="Owner action is overdue." if overdue else "Owner action is due within seven days.",
        guidance="Review ownership, deadline, and the next lifecycle action.",
        action_label="Open document",
        action_path=f"/compdocs/{document.project.slug}?document={document.pk}",
        occurred_at=timezone.now(),
        due_at=_due_datetime(document.next_action_due_date),
    )


def _review_item(item_factory, task):
    overdue = task.due_date < timezone.localdate()
    return item_factory(
        identifier=f"compliance-review:{task.pk}",
        kind=f"compliance_{task.kind}",
        severity="critical" if overdue else "warning",
        title=f"{task.get_kind_display()} decision required",
        detail="Assigned decision is overdue." if overdue else "Assigned decision is due soon.",
        guidance="Open the document, review its evidence, and record a decision.",
        action_label="Open review",
        action_path=(
            f"/compdocs/{task.document.project.slug}?document={task.document_id}"
        ),
        occurred_at=task.created_at,
        due_at=_due_datetime(task.due_date),
    )


def _revision_item(item_factory, profile):
    document = profile.document
    return item_factory(
        identifier=f"compliance-revision:{profile.pk}:{profile.docproof_issue}",
        kind="compliance_revision",
        severity="warning",
        title=f"DocProof revision: {document.name}",
        detail=f"DocProof issue {profile.docproof_issue} differs from the tracked document issue.",
        guidance="Review the published revision and update the compliance evidence.",
        action_label="Open tracking",
        action_path=f"/compdocs/{document.project.slug}?document={document.pk}",
        occurred_at=profile.docproof_checked_at or profile.updated_at,
        due_at=None,
    )


def _notification_failure_item(item_factory, log):
    document = log.profile.document
    return item_factory(
        identifier=f"compliance-notification:{log.pk}",
        kind="compliance_notification",
        severity="warning",
        title=f"Notification delivery: {document.name}",
        detail="A compliance notification could not be delivered.",
        guidance="Review recipients and mail availability before the next retry.",
        action_label="Open tracking",
        action_path=f"/compdocs/{document.project.slug}?document={document.pk}",
        occurred_at=log.updated_at,
        due_at=log.next_attempt_at,
    )


def _due_datetime(value):
    return timezone.make_aware(datetime.combine(value, time.min))
