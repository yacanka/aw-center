"""Shared CompDoc history-version queries for DCC traceability."""

from django.db.models import Exists, OuterRef, Q, Subquery

from common.compdoc_versions import latest_history_id
from .compdoc_capture import captured_model_field_names
from .models import DccCompdocTrace


def recent_current_versions(model, project_slug, boundary, limit):
    """Return bounded current versions changed recently and linked to a DCC."""

    history = model.history.model.objects
    newer_version = history.filter(id=OuterRef("id")).filter(
        Q(history_date__gt=OuterRef("history_date"))
        | Q(
            history_date=OuterRef("history_date"),
            history_id__gt=OuterRef("history_id"),
        )
    )
    traced_ids = DccCompdocTrace.objects.filter(project_slug=project_slug).values(
        "compdoc_id"
    )
    return list(
        history.filter(
            history_date__gte=boundary,
            id__in=Subquery(traced_ids),
        )
        .annotate(has_newer_version=Exists(newer_version))
        .filter(has_newer_version=False)
        .exclude(history_type="-")
        .only(
            "id", "history_id", "history_date",
            *captured_model_field_names(model),
        )
        .order_by("-history_date", "-history_id")[:limit]
    )
