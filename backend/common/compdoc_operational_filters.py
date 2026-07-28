"""Operational quick filters for project compliance-document lists."""

from datetime import timedelta

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from common.compdoc_lifecycle_models import CompDocReviewTask


def apply_compdoc_search(queryset, raw_search):
    """Search bounded identity fields that exist on the concrete project model."""

    search = str(raw_search or "").strip()[:100]
    if not search:
        return queryset
    field_names = {field.name for field in queryset.model._meta.fields}
    lookup = Q()
    for name in ("name", "cover_page_no", "tech_doc_no", "tech_doc_no_2"):
        if name in field_names:
            lookup |= Q(**{f"{name}__icontains": search})
    return queryset.filter(lookup)


def apply_compdoc_operational_filters(request, queryset, model):
    """Apply bounded ownership, deadline, and pending-task quick filters."""

    query = request.query_params
    if query.get("mine") == "true":
        queryset = queryset.filter(owner=request.user)
    if query.get("my_team") == "true":
        queryset = queryset.filter(owner_group__in=request.user.groups.all())
    if query.get("unassigned") == "true":
        queryset = queryset.filter(owner__isnull=True, owner_group__isnull=True)
    queryset = _apply_due_filter(queryset, query.get("due"))
    return _apply_review_filter(queryset, model, query.get("review"))


def _apply_due_filter(queryset, due):
    today = timezone.localdate()
    if due == "overdue":
        return queryset.filter(next_action_due_date__lt=today)
    if due == "soon":
        return queryset.filter(
            next_action_due_date__range=(today, today + timedelta(days=7))
        )
    return queryset


def _apply_review_filter(queryset, model, review_kind):
    if review_kind not in CompDocReviewTask.Kind.values:
        return queryset
    pending = CompDocReviewTask.objects.filter(
        project_slug=model._meta.app_label,
        document_id=OuterRef("pk"),
        kind=review_kind,
        status=CompDocReviewTask.Status.PENDING,
    )
    return queryset.annotate(has_pending_review=Exists(pending)).filter(
        has_pending_review=True
    )
