"""Lease-fenced delivery of durable Watcher reminder emails."""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from integrations.mail import MailUnavailable, send_html_email

from .models import DccReminderDelivery

LOGGER = logging.getLogger(__name__)


def process_dcc_reminder_deliveries():
    sent = failed = 0
    claims = claim_dcc_reminders()
    for delivery_id, lease_token in claims:
        if deliver_dcc_reminder(delivery_id, lease_token):
            sent += 1
        else:
            failed += 1
    return {"processed": len(claims), "sent": sent, "failed": failed}


@transaction.atomic
def claim_dcc_reminders(*, now=None):
    current_time = now or timezone.now()
    queryset = DccReminderDelivery.objects.filter(
        Q(status=DccReminderDelivery.Status.PENDING)
        | Q(status=DccReminderDelivery.Status.FAILED, next_attempt_at__lte=current_time)
        | Q(status=DccReminderDelivery.Status.CLAIMED, claim_expires_at__lte=current_time)
    ).order_by("created_at", "id")
    queryset = (
        queryset.select_for_update(skip_locked=True)
        if connection.features.has_select_for_update_skip_locked
        else queryset.select_for_update()
    )
    batch_size = max(int(settings.COMPDOC_NOTIFICATION_BATCH_SIZE), 1)
    claims = []
    for delivery in list(queryset[:batch_size]):
        token = uuid.uuid4()
        delivery.status = DccReminderDelivery.Status.CLAIMED
        delivery.lease_token = token
        delivery.claimed_at = current_time
        delivery.claim_expires_at = current_time + timedelta(minutes=15)
        delivery.next_attempt_at = None
        delivery.attempt_count += 1
        delivery.error_code = ""
        delivery.save(
            update_fields=(
                "status",
                "lease_token",
                "claimed_at",
                "claim_expires_at",
                "next_attempt_at",
                "attempt_count",
                "error_code",
                "updated_at",
            )
        )
        claims.append((delivery.pk, token))
    return claims


def deliver_dcc_reminder(delivery_id, lease_token):
    try:
        delivery = DccReminderDelivery.objects.get(
            pk=delivery_id,
            status=DccReminderDelivery.Status.CLAIMED,
            lease_token=lease_token,
        )
    except DccReminderDelivery.DoesNotExist:
        return False
    try:
        body = render_to_string("dcc/reminder_email.html", delivery.context)
        send_html_email(
            delivery.subject,
            body,
            delivery.recipients,
            message_id=delivery.message_id,
        )
    except MailUnavailable:
        return finish_failure(delivery_id, lease_token, "MAIL_TRANSPORT_UNAVAILABLE")
    except Exception as error:
        LOGGER.warning(
            "DCC reminder delivery failed.",
            extra={"delivery_id": str(delivery_id), "error_type": type(error).__name__},
        )
        return finish_failure(delivery_id, lease_token, "MAIL_DELIVERY_FAILED")
    return finish_success(delivery_id, lease_token)


@transaction.atomic
def finish_success(delivery_id, lease_token):
    delivery = DccReminderDelivery.objects.filter(
        pk=delivery_id,
        status=DccReminderDelivery.Status.CLAIMED,
        lease_token=lease_token,
    ).first()
    if delivery is None:
        return False
    delivery.status = DccReminderDelivery.Status.SENT
    delivery.recipient_count = len(delivery.recipients)
    delivery.error_code = ""
    delivery.lease_token = None
    delivery.claim_expires_at = None
    delivery.next_attempt_at = None
    delivery.sent_at = timezone.now()
    delivery.save()
    return True


@transaction.atomic
def finish_failure(delivery_id, lease_token, error_code):
    updated = DccReminderDelivery.objects.filter(
        pk=delivery_id,
        status=DccReminderDelivery.Status.CLAIMED,
        lease_token=lease_token,
    ).update(
        status=DccReminderDelivery.Status.FAILED,
        error_code=error_code,
        lease_token=None,
        claim_expires_at=None,
        next_attempt_at=timezone.now()
        + timedelta(seconds=max(int(settings.COMPDOC_NOTIFICATION_RETRY_SECONDS), 30)),
    )
    return False if updated else False
