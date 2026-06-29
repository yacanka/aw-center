"""Rate limiting helpers for DCC reminder emails."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dcc.models import JIRA_DCC

REMINDER_EMAIL_COOLDOWN = timedelta(hours=1)


def get_reminder_wait_seconds(dcc_record, current_time=None):
    """Return remaining cooldown seconds for a DCC reminder email."""
    if not dcc_record.last_reminder_mail_sent_at:
        return 0
    current_time = current_time or timezone.now()
    next_allowed_time = dcc_record.last_reminder_mail_sent_at + REMINDER_EMAIL_COOLDOWN
    remaining_seconds = (next_allowed_time - current_time).total_seconds()
    return max(0, int(remaining_seconds))


def reserve_reminder_email_slot(dcc_record, current_time=None):
    """Atomically reserve the hourly reminder email slot for one DCC record."""
    current_time = current_time or timezone.now()
    cooldown_boundary = current_time - REMINDER_EMAIL_COOLDOWN
    updated_count = _update_available_record(dcc_record.pk, current_time, cooldown_boundary)
    if updated_count:
        dcc_record.last_reminder_mail_sent_at = current_time
        return 0
    dcc_record.refresh_from_db(fields=["last_reminder_mail_sent_at"])
    return get_reminder_wait_seconds(dcc_record, current_time)


@transaction.atomic
def _update_available_record(record_id, current_time, cooldown_boundary):
    return JIRA_DCC.objects.filter(
        Q(last_reminder_mail_sent_at__isnull=True)
        | Q(last_reminder_mail_sent_at__lte=cooldown_boundary),
        pk=record_id,
    ).update(last_reminder_mail_sent_at=current_time)
