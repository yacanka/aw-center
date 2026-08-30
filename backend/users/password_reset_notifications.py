"""Durable and fenced password-reset email delivery."""

import logging
import secrets
import time
import uuid
from datetime import timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from integrations.mail import MailUnavailable, send_html_email

from .models import PasswordResetDelivery
from .password_reset_tokens import (
    account_state_digest,
    current_token_timestamp,
    make_token_at,
)


LOGGER = logging.getLogger(__name__)
User = get_user_model()
REQUEST_COOLDOWN_SECONDS = 60
LEASE_SECONDS = 15 * 60
RETRY_SECONDS = 5 * 60
MIN_PUBLIC_RESPONSE_SECONDS = 0.2


def pad_password_reset_response(started_at):
    """Mask the normal known/unknown-account database timing difference."""

    remaining = MIN_PUBLIC_RESPONSE_SECONDS - (time.monotonic() - started_at)
    if remaining > 0:
        time.sleep(remaining)


@transaction.atomic
def enqueue_password_reset(user):
    """Materialize at most one live delivery for the current account state."""

    locked_user = User.objects.select_for_update().get(pk=user.pk)
    if not locked_user.is_active or not locked_user.email:
        return None, False

    now = timezone.now()
    state_digest = account_state_digest(locked_user)
    token_cutoff = now - timedelta(seconds=max(int(settings.PASSWORD_RESET_TIMEOUT), 1))
    active = PasswordResetDelivery.objects.filter(
        user=locked_user,
        state_digest=state_digest,
        token_timestamp__isnull=False,
        requested_at__gt=token_cutoff,
        status__in=(
            PasswordResetDelivery.Status.PENDING,
            PasswordResetDelivery.Status.CLAIMED,
            PasswordResetDelivery.Status.FAILED,
        ),
    ).order_by("requested_at")
    existing = active.first()
    if existing is not None:
        return existing, False

    recent_sent = PasswordResetDelivery.objects.filter(
        user=locked_user,
        state_digest=state_digest,
        status=PasswordResetDelivery.Status.SENT,
        requested_at__gte=now - timedelta(seconds=REQUEST_COOLDOWN_SECONDS),
    ).first()
    if recent_sent is not None:
        return recent_sent, False

    delivery_id = uuid.uuid4()
    delivery = PasswordResetDelivery.objects.create(
        id=delivery_id,
        user=locked_user,
        state_digest=state_digest,
        token_timestamp=current_token_timestamp(),
        message_id=f"<password-reset-{delivery_id.hex}@awcenter>",
        requested_at=now,
    )
    return delivery, True


def process_password_reset_deliveries():
    """Claim and deliver one bounded password-reset batch."""

    sent = failed = 0
    claims = claim_password_reset_deliveries()
    for delivery_id, lease_token in claims:
        outcome = deliver_password_reset(delivery_id, lease_token)
        if outcome == PasswordResetDelivery.Status.SENT:
            sent += 1
        elif outcome == PasswordResetDelivery.Status.FAILED:
            failed += 1
    return {"processed": len(claims), "sent": sent, "failed": failed}


@transaction.atomic
def claim_password_reset_deliveries(*, now=None):
    """Fence pending, retryable, or abandoned deliveries."""

    current_time = now or timezone.now()
    queryset = PasswordResetDelivery.objects.filter(
        Q(status=PasswordResetDelivery.Status.PENDING)
        | Q(
            status=PasswordResetDelivery.Status.FAILED,
            next_attempt_at__lte=current_time,
        )
        | Q(
            status=PasswordResetDelivery.Status.CLAIMED,
            claim_expires_at__lte=current_time,
        )
    ).order_by("requested_at", "id")
    if connection.features.has_select_for_update_skip_locked:
        queryset = queryset.select_for_update(skip_locked=True)
    else:
        queryset = queryset.select_for_update()
    batch_size = max(int(settings.COMPDOC_NOTIFICATION_BATCH_SIZE), 1)
    deliveries = list(queryset[:batch_size])
    claims = []
    for delivery in deliveries:
        token = uuid.uuid4()
        delivery.status = PasswordResetDelivery.Status.CLAIMED
        delivery.lease_token = token
        delivery.claimed_at = current_time
        delivery.claim_expires_at = current_time + timedelta(seconds=LEASE_SECONDS)
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


def deliver_password_reset(delivery_id, lease_token):
    """Deliver only while the supplied lease owns the outbox row."""

    try:
        delivery = PasswordResetDelivery.objects.select_related("user").get(
            pk=delivery_id,
            status=PasswordResetDelivery.Status.CLAIMED,
            lease_token=lease_token,
        )
    except PasswordResetDelivery.DoesNotExist:
        return None

    cancellation_code = _cancellation_code(delivery)
    if cancellation_code:
        return _finish_cancelled(delivery_id, lease_token, cancellation_code)

    try:
        body = _render_password_reset(delivery)
        send_html_email(
            "Şifre sıfırlama",
            body,
            [delivery.user.email],
            message_id=delivery.message_id,
        )
    except MailUnavailable:
        return _finish_failure(delivery_id, lease_token, "MAIL_TRANSPORT_UNAVAILABLE")
    except Exception as exc:
        LOGGER.warning(
            "Password-reset notification delivery failed.",
            extra={
                "delivery_id": str(delivery_id),
                "error_type": type(exc).__name__,
            },
        )
        return _finish_failure(delivery_id, lease_token, "MAIL_DELIVERY_FAILED")
    return _finish_success(delivery_id, lease_token)


def _cancellation_code(delivery):
    user = delivery.user
    if not user.is_active or not user.email:
        return "ACCOUNT_UNAVAILABLE"
    if timezone.now() >= delivery.requested_at + timedelta(
        seconds=max(int(settings.PASSWORD_RESET_TIMEOUT), 1)
    ):
        return "TOKEN_EXPIRED_BEFORE_DELIVERY"
    if not secrets.compare_digest(delivery.state_digest, account_state_digest(user)):
        return "ACCOUNT_STATE_CHANGED"
    return ""


def _render_password_reset(delivery):
    uid = urlsafe_base64_encode(force_bytes(delivery.user_id))
    token = make_token_at(delivery.user, delivery.token_timestamp)
    reset_url = urlsplit(settings.FRONTEND_RESET_URL)
    fragmentless_url = urlunsplit(
        (reset_url.scheme, reset_url.netloc, reset_url.path, reset_url.query, "")
    )
    reset_link = f"{fragmentless_url}#{urlencode({'uid': uid, 'token': token})}"
    return render_to_string(
        "users/password_reset.html",
        {"reset_link": reset_link},
    )


@transaction.atomic
def _finish_success(delivery_id, lease_token):
    updated = PasswordResetDelivery.objects.filter(
        pk=delivery_id,
        status=PasswordResetDelivery.Status.CLAIMED,
        lease_token=lease_token,
    ).update(
        status=PasswordResetDelivery.Status.SENT,
        error_code="",
        lease_token=None,
        claim_expires_at=None,
        next_attempt_at=None,
        sent_at=timezone.now(),
    )
    return PasswordResetDelivery.Status.SENT if updated == 1 else None


@transaction.atomic
def _finish_failure(delivery_id, lease_token, error_code):
    updated = PasswordResetDelivery.objects.filter(
        pk=delivery_id,
        status=PasswordResetDelivery.Status.CLAIMED,
        lease_token=lease_token,
    ).update(
        status=PasswordResetDelivery.Status.FAILED,
        error_code=error_code,
        lease_token=None,
        claim_expires_at=None,
        next_attempt_at=timezone.now() + timedelta(seconds=RETRY_SECONDS),
    )
    return PasswordResetDelivery.Status.FAILED if updated == 1 else None


@transaction.atomic
def _finish_cancelled(delivery_id, lease_token, error_code):
    updated = PasswordResetDelivery.objects.filter(
        pk=delivery_id,
        status=PasswordResetDelivery.Status.CLAIMED,
        lease_token=lease_token,
    ).update(
        status=PasswordResetDelivery.Status.CANCELLED,
        error_code=error_code,
        lease_token=None,
        claim_expires_at=None,
        next_attempt_at=None,
        cancelled_at=timezone.now(),
    )
    return PasswordResetDelivery.Status.CANCELLED if updated == 1 else None
