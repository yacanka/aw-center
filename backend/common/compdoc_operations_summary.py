"""Shared compliance-document operational counters."""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from common.compdoc_lifecycle_models import CompDocReviewTask


def build_operational_summary(model, today=None):
    """Return existing operational definitions for dashboards and saved reporting."""
    today = today or timezone.localdate()
    documents = model.objects.aggregate(
        unassigned=Count(
            "pk",
            filter=Q(is_archived=False, owner__isnull=True, owner_group__isnull=True),
        ),
        action_overdue=Count(
            "pk", filter=Q(is_archived=False, next_action_due_date__lt=today)
        ),
        action_due_soon=Count(
            "pk",
            filter=Q(
                is_archived=False,
                next_action_due_date__range=(today, today + timedelta(days=7)),
            ),
        ),
        archived=Count("pk", filter=Q(is_archived=True)),
    )
    reviews = CompDocReviewTask.objects.filter(
        project_slug=model._meta.app_label,
        status=CompDocReviewTask.Status.PENDING,
    ).aggregate(
        pending_review=Count("pk", filter=Q(kind=CompDocReviewTask.Kind.REVIEW)),
        pending_approval=Count("pk", filter=Q(kind=CompDocReviewTask.Kind.APPROVAL)),
    )
    return {
        **documents,
        **reviews,
        "filters": {
            "unassigned": {"unassigned": "true"},
            "action_overdue": {"due": "overdue"},
            "action_due_soon": {"due": "soon"},
            "pending_review": {"review": "review"},
            "pending_approval": {"review": "approval"},
            "archived": {"archived": "true"},
        },
    }
