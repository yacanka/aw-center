"""Durable, deterministic compliance notification delivery."""

import hashlib
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from orgs.models import Person
from integrations.mail import MailUnavailable, send_html_email

from .models import NotificationLog, NotificationPolicy, TrackingProfile


LOGGER = logging.getLogger(__name__)
SUPPORTED_EVENTS = frozenset(("overdue", "due_soon", "revision_available"))
DUE_SOON_DAYS = 7


def scan_notifications(*, project_slug=None):
    """Materialize active events, then claim and deliver a bounded batch."""

    profiles = TrackingProfile.objects.filter(
        notification_enabled=True,
        document__is_archived=False,
        document__project__enabled=True,
    ).select_related("document", "document__project", "document__panel")
    if project_slug:
        profiles = profiles.filter(document__project__slug=project_slug)

    materialized = 0
    for profile in profiles.iterator(chunk_size=100):
        materialized += materialize_profile_events(profile)
        TrackingProfile.objects.filter(pk=profile.pk).update(
            notification_checked_at=timezone.now()
        )

    sent = failed = 0
    for log_id, lease_token in claim_notifications():
        if deliver_notification(log_id, lease_token):
            sent += 1
        else:
            failed += 1
    return {
        "processed": materialized + sent + failed,
        "materialized": materialized,
        "sent": sent,
        "failed": failed,
    }


def materialize_profile_events(profile, *, today=None):
    """Create at most one durable delivery record per event evidence value."""

    policy = NotificationPolicy.objects.filter(
        project=profile.document.project,
        is_active=True,
    ).first()
    created = 0
    for event_type, evidence in detect_events(profile, today=today).items():
        if event_type not in set(profile.notification_events or []):
            continue
        if policy and not policy.event_rules.get(event_type, {}).get("enabled", True):
            continue
        raw_key = f"{profile.pk}:{event_type}:{evidence}"
        event_key = hashlib.sha256(raw_key.encode()).hexdigest()
        message_id = f"<{event_key}@awcenter>"
        _log, was_created = NotificationLog.objects.get_or_create(
            event_key=event_key,
            defaults={
                "profile": profile,
                "event_type": event_type,
                "message_id": message_id,
            },
        )
        created += int(was_created)
    return created


def detect_events(profile, *, today=None):
    document = profile.document
    current_day = today or timezone.localdate()
    events = {}
    target = document.ubm_target_date
    if document.status == "to_be_issued" and target:
        remaining_days = (target - current_day).days
        if remaining_days < 0:
            events["overdue"] = target.isoformat()
        elif remaining_days <= DUE_SOON_DAYS:
            events["due_soon"] = target.isoformat()
    if profile.docproof_status == "revision_available" and profile.docproof_issue:
        events["revision_available"] = profile.docproof_issue
    return events


@transaction.atomic
def claim_notifications(*, now=None):
    """Fence pending or expired claims and return opaque claim pairs."""

    current_time = now or timezone.now()
    queryset = NotificationLog.objects.filter(
        Q(status=NotificationLog.Status.PENDING)
        | Q(status=NotificationLog.Status.FAILED, next_attempt_at__lte=current_time)
        | Q(status=NotificationLog.Status.CLAIMED, claim_expires_at__lte=current_time)
    ).order_by("created_at", "id")
    if connection.features.has_select_for_update_skip_locked:
        queryset = queryset.select_for_update(skip_locked=True)
    else:
        queryset = queryset.select_for_update()
    logs = list(queryset[: max(int(settings.COMPDOC_NOTIFICATION_BATCH_SIZE), 1)])
    claimed = []
    for log in logs:
        token = uuid.uuid4()
        log.status = NotificationLog.Status.CLAIMED
        log.lease_token = token
        log.claimed_at = current_time
        log.claim_expires_at = current_time + timedelta(
            seconds=max(int(settings.COMPDOC_NOTIFICATION_LOCK_SECONDS), 30)
        )
        log.attempt_count += 1
        log.error_code = ""
        log.save(
            update_fields=(
                "status",
                "lease_token",
                "claimed_at",
                "claim_expires_at",
                "attempt_count",
                "error_code",
                "updated_at",
            )
        )
        claimed.append((log.pk, token))
    return claimed


def deliver_notification(log_id, lease_token):
    """Send one claimed message and complete it only while its fence is owned."""

    try:
        log = NotificationLog.objects.select_related(
            "profile__document__project",
            "profile__document__panel",
        ).get(pk=log_id, status=NotificationLog.Status.CLAIMED, lease_token=lease_token)
        recipients = resolve_recipients(log.profile)
        if not recipients:
            return _finish_failure(log_id, lease_token, "NO_RECIPIENTS")
        send_notification_email(log, recipients)
        return _finish_success(log_id, lease_token, len(recipients))
    except NotificationLog.DoesNotExist:
        return False
    except MailUnavailable:
        return _finish_failure(log_id, lease_token, "MAIL_TRANSPORT_UNAVAILABLE")
    except Exception:
        LOGGER.exception(
            "Compliance notification delivery failed.",
            extra={"notification_id": str(log_id)},
        )
        return _finish_failure(log_id, lease_token, "MAIL_DELIVERY_FAILED")


def resolve_recipients(profile):
    document = profile.document
    if not document.panel_id:
        return []
    people = Person.objects.filter(
        responsible_assignments__panel_id=document.panel_id,
    ).exclude(email="")
    if profile.responsible_mode == TrackingProfile.ResponsibleMode.CUSTOM:
        people = people.filter(pk__in=profile.responsible_people.values("pk"))
    return sorted(set(people.values_list("email", flat=True)))


def send_notification_email(log, recipients):
    document = log.profile.document
    context = {
        "document": document,
        "event_type": log.event_type,
        "project": document.project,
    }
    body = render_to_string("compliance/compdoc_notification.html", context)
    send_html_email(
        f"AW Center compliance alert: {document.name}",
        body,
        recipients,
        message_id=log.message_id,
    )


@transaction.atomic
def _finish_success(log_id, lease_token, recipient_count):
    updated = NotificationLog.objects.filter(
        pk=log_id,
        status=NotificationLog.Status.CLAIMED,
        lease_token=lease_token,
    ).update(
        status=NotificationLog.Status.SENT,
        recipient_count=recipient_count,
        error_code="",
        lease_token=None,
        claim_expires_at=None,
        next_attempt_at=None,
        sent_at=timezone.now(),
    )
    return updated == 1


@transaction.atomic
def _finish_failure(log_id, lease_token, error_code):
    updated = NotificationLog.objects.filter(
        pk=log_id,
        status=NotificationLog.Status.CLAIMED,
        lease_token=lease_token,
    ).update(
        status=NotificationLog.Status.FAILED,
        error_code=error_code,
        lease_token=None,
        claim_expires_at=None,
        next_attempt_at=timezone.now()
        + timedelta(seconds=max(int(settings.COMPDOC_NOTIFICATION_RETRY_SECONDS), 30)),
    )
    return False if updated == 1 else False
