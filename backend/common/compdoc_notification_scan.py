"""Bounded periodic scanning for enabled compliance-document notifications."""

import logging
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from common.compdoc_notifications import process_profile
from common.compdoc_tracking_models import CompDocTrackingProfile
from projects.registry import PROJECT_DEFINITIONS

LOCK_KEY = "compdoc-notification-scan"
LOGGER = logging.getLogger(__name__)


def scan_enabled_profiles(project_slug=None, limit=None):
    """Process a bounded set of enabled profiles under a distributed cache lock."""

    batch_size = limit or settings.COMPDOC_NOTIFICATION_BATCH_SIZE
    lock_token = uuid4().hex
    if not cache.add(LOCK_KEY, lock_token, timeout=settings.COMPDOC_NOTIFICATION_LOCK_SECONDS):
        return {"processed": 0, "sent": 0, "failed": 0, "locked": True}
    try:
        return _scan(project_slug, max(1, int(batch_size)))
    finally:
        if cache.get(LOCK_KEY) == lock_token:
            cache.delete(LOCK_KEY)


def _scan(project_slug, limit):
    profiles = CompDocTrackingProfile.objects.filter(notification_enabled=True)
    if project_slug:
        profiles = profiles.filter(project_slug=project_slug)
    totals = {"processed": 0, "sent": 0, "failed": 0, "locked": False}
    ordered = profiles.select_related("updated_by").order_by(
        "notification_checked_at", "created_at"
    )
    for profile in ordered[:limit]:
        results = _process_safely(profile)
        totals["processed"] += 1
        totals["sent"] += sum(item["status"] == "sent" for item in results)
        totals["failed"] += sum(item["status"] == "failed" for item in results)
    return totals


def _process_one(profile):
    definition = PROJECT_DEFINITIONS.get(profile.project_slug)
    if not definition or "compdocs" not in definition.capabilities:
        return []
    model = apps.get_model(profile.project_slug, "CompDoc")
    document = model.objects.filter(pk=profile.document_id, is_archived=False).first()
    if not document:
        if not model.objects.filter(pk=profile.document_id).exists():
            profile.delete()
        return []
    results = process_profile(model, document, profile)
    profile.notification_checked_at = timezone.now()
    profile.save(update_fields=["notification_checked_at", "updated_at"])
    return results


def _process_safely(profile):
    try:
        return _process_one(profile)
    except Exception:
        LOGGER.exception(
            "CompDoc notification profile failed.",
            extra={"profile_id": str(profile.pk)},
        )
        CompDocTrackingProfile.objects.filter(pk=profile.pk).update(
            notification_checked_at=timezone.now()
        )
        return [{"status": "failed"}]
