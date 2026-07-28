"""Idempotent HTML notifications for tracked compliance documents."""

import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.exceptions import APIException

from common.compdoc_docproof import check_docproof
from common.compdoc_notification_events import detect_events, event_started_at
from common.compdoc_notification_policy import (
    delivery_occurrence,
    partition_contacts,
    retry_due,
)
from common.compdoc_tracking import resolve_contacts
from common.compdoc_tracking_models import CompDocNotificationLog
from dcc.service.MailSender import SendMail

LOGGER = logging.getLogger(__name__)


def send_notification(model, document, profile, event_type):
    """Send one event once per stable document/event evidence value."""

    active_events = detect_events(document, profile)
    if event_type not in active_events:
        return {"status": "not_applicable", "event_type": event_type}
    content = build_notification_content(model, document, profile, event_type)
    log, created = _notification_log(
        document, profile, event_type, active_events[event_type], content
    )
    if not created and not retry_due(log, content["rule"]):
        return {"status": "already_processed", "event_type": event_type}
    return _deliver(content, log, event_type)


def build_notification_content(model, document, profile, event_type):
    """Render the shared subject, HTML body, and current responsible addresses."""

    contacts = resolve_contacts(model, document, profile)
    plan = partition_contacts(
        model._meta.app_label, event_type, contacts, document, profile
    )
    primary = _contact_emails(plan["primary"])
    escalation = _contact_emails(plan["escalation"])
    context = _template_context(model, document, profile, event_type)
    return {
        "subject": context["subject"],
        "html_body": render_to_string("common/compdoc_notification.html", context),
        "recipients": sorted(set(primary + escalation)),
        "to_recipients": primary,
        "cc_recipients": escalation,
        "policy_version": plan["version"],
        "rule": plan["rule"],
    }


def process_profile(model, document, profile):
    """Refresh required evidence and process configured active events."""

    if "revision_available" in profile.notification_events and _docproof_refresh_due(profile):
        try:
            profile = check_docproof(model, document, profile.updated_by)
        except APIException:
            pass
    return [
        send_notification(model, document, profile, event)
        for event in profile.notification_events
    ]


def _deliver(content, log, event_type):
    recipients = content["recipients"]
    delivered = _send_content(content, log, event_type, recipients)
    _apply_delivery_result(content, log, delivered, recipients)
    return {"status": log.status, "event_type": event_type, "recipient_count": len(recipients)}


def _send_content(content, log, event_type, recipients):
    try:
        return bool(recipients) and SendMail(
            content["subject"],
            content["html_body"],
            ";".join(content["to_recipients"]),
            ";".join(content["cc_recipients"]),
        )
    except Exception:
        LOGGER.exception(
            "CompDoc notification delivery failed.",
            extra={"profile_id": str(log.profile_id), "event_type": event_type},
        )
        return False


def _apply_delivery_result(content, log, delivered, recipients):
    log.recipient_count = len(recipients)
    log.primary_recipient_count = len(content["to_recipients"])
    log.escalation_recipient_count = len(content["cc_recipients"])
    log.policy_version = content["policy_version"]
    log.attempt_count += 1
    log.status = "sent" if delivered else "failed"
    log.error_code = "" if delivered else "COMPDOC_NOTIFICATION_DELIVERY_UNAVAILABLE"
    log.sent_at = timezone.now() if delivered else None
    log.save()


def _template_context(model, document, profile, event_type):
    labels = {
        "overdue": "Delivery is overdue",
        "due_soon": "Delivery is approaching",
        "revision_available": "A new DocProof revision is available",
    }
    project = model._meta.app_label.upper()
    subject = f"[{project}] {labels[event_type]}: {document.name}"
    return {
        "subject": " ".join(subject.splitlines())[:255],
        "heading": labels[event_type],
        "project": project,
        "document": document,
        "docproof_issue": profile.docproof_issue,
        "generated_at": timezone.localtime(),
    }


def _event_key(profile, event_type, evidence, occurrence):
    raw = f"{profile.project_slug}:{profile.document_id}:{event_type}:{evidence}:{occurrence}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _notification_log(document, profile, event_type, evidence, content):
    occurrence = delivery_occurrence(
        content["rule"], event_started_at(document, profile, event_type)
    )
    event_key = _event_key(profile, event_type, evidence, occurrence)
    return CompDocNotificationLog.objects.get_or_create(
        event_key=event_key,
        defaults={
            "profile": profile,
            "event_type": event_type,
            "policy_version": content["policy_version"],
        },
    )


def _contact_emails(contacts):
    return sorted({contact["email"] for contact in contacts if contact["email"]})


def _docproof_refresh_due(profile):
    if not profile.docproof_checked_at:
        return True
    interval = timedelta(seconds=settings.COMPDOC_DOCPROOF_REFRESH_SECONDS)
    return profile.docproof_checked_at <= timezone.now() - interval
