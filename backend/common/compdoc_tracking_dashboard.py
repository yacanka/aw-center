"""Content-free tracking metrics for the Compliance Documents dashboard."""

from django.db.models import Count, Q

from common.compdoc_tracking_models import CompDocTrackingProfile


def build_tracking_summary(model):
    """Return one-query project tracking and delivery exception counts."""

    active_ids = model.objects.filter(is_archived=False).values("pk")
    profiles = CompDocTrackingProfile.objects.filter(
        project_slug=model._meta.app_label, document_id__in=active_ids
    )
    return profiles.aggregate(
        configured_count=Count("id", distinct=True),
        notification_enabled_count=Count(
            "id", filter=Q(notification_enabled=True), distinct=True
        ),
        revision_available_count=Count(
            "id", filter=Q(docproof_status="revision_available"), distinct=True
        ),
        delivery_failure_count=Count(
            "notification_logs", filter=Q(notification_logs__status="failed"), distinct=True
        ),
    )
