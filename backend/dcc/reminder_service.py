"""Create durable Watcher reminder snapshots without exposing mail credentials."""

import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from integrations.jira.sessions import jira_connector_for
from jobs.services import IdempotencyConflict, require_idempotency_key

from .access_policy import OPERATOR, require_resource_role
from .document_fields import field
from .document_snapshot import DccSnapshotError, validate_parent_issue
from .models import DccRecord, DccReminderDelivery
from .services.jira_links import build_jira_issue_url
from .services.project_resolver import DccProjectResolutionError, resolve_projects_from_jira_components

REMINDER_COOLDOWN = timedelta(hours=1)
MAX_RECIPIENTS = 200


class DccReminderCooldown(APIException):
    status_code = 429
    default_code = "DCC_REMINDER_COOLDOWN"
    default_detail = "A reminder for this DCC record was already queued recently."

    def __init__(self, retry_after_seconds):
        super().__init__(
            {
                "detail": self.default_detail,
                "code": self.default_code,
                "retry_after_seconds": max(1, int(retry_after_seconds)),
            }
        )


def enqueue_dcc_reminder(actor, record_id, values, idempotency_key):
    """Read current JIRA recipients and atomically materialize one mail outbox row."""

    key = require_idempotency_key(idempotency_key)
    existing = DccReminderDelivery.objects.filter(
        requested_by=actor,
        idempotency_key=key,
    ).first()
    if existing:
        verify_replay(existing, record_id, values)
        return existing, False

    record = DccRecord.objects.prefetch_related("projects", "assigned_users").get(pk=record_id)
    require_resource_role(actor, record, OPERATOR)
    require_active_record(record)
    require_current_version(record, values["version"])
    snapshot = build_reminder_snapshot(actor, record, values)
    try:
        with transaction.atomic():
            locked = DccRecord.objects.select_for_update().prefetch_related(
                "projects", "assigned_users"
            ).get(pk=record_id)
            require_resource_role(actor, locked, OPERATOR)
            require_active_record(locked)
            require_current_version(locked, values["version"])
            existing = DccReminderDelivery.objects.filter(
                requested_by=actor,
                idempotency_key=key,
            ).first()
            if existing:
                verify_replay(existing, record_id, values)
                return existing, False
            recent = DccReminderDelivery.objects.filter(
                record=locked,
                created_at__gte=timezone.now() - REMINDER_COOLDOWN,
            ).order_by("-created_at").first()
            if recent:
                retry_at = recent.created_at + REMINDER_COOLDOWN
                raise DccReminderCooldown((retry_at - timezone.now()).total_seconds())
            delivery_id = uuid.uuid4()
            delivery = DccReminderDelivery.objects.create(
                id=delivery_id,
                record=locked,
                requested_by=actor,
                idempotency_key=key,
                message_id=f"<dcc-reminder-{delivery_id.hex}@awcenter>",
                subject=snapshot["subject"],
                context=snapshot["context"],
                recipients=snapshot["recipients"],
            )
        return delivery, True
    except IntegrityError:
        existing = DccReminderDelivery.objects.filter(
            requested_by=actor,
            idempotency_key=key,
        ).first()
        if existing is None:
            raise
        verify_replay(existing, record_id, values)
        return existing, False


def build_reminder_snapshot(actor, record, values):
    connector = jira_connector_for(actor)
    connector.set_issue(record.issue)
    issue = connector.get_issue()
    validate_parent_issue(issue)
    try:
        definitions = resolve_projects_from_jira_components(field(issue.fields, "components"))
    except DccProjectResolutionError as error:
        raise DccSnapshotError(
            "The JIRA task does not identify a supported DCC project.",
            "DCC_PROJECT_INVALID",
        ) from error
    jira_slugs = {definition.slug for definition in definitions}
    record_slugs = set(record.projects.values_list("slug", flat=True))
    if jira_slugs != record_slugs:
        raise ValidationError(
            {"record": "The DCC record projects no longer match the JIRA task."}
        )
    recipients = reminder_recipients(connector.get_open_subtask(MAX_RECIPIENTS))
    if not recipients:
        raise ValidationError(
            {"recipients": "No valid email address exists on an open JIRA subtask assignee."}
        )
    labels = sorted({
        str(definition.dcc_label or definition.jira_component or definition.slug)
        for definition in definitions
    })
    return {
        "subject": f"[{', '.join(labels)}] CCB - {values['ccb_no']} toplantı gündemi",
        "recipients": recipients,
        "context": {
            "issue": record.issue,
            "title": record.title,
            "jira_url": build_jira_issue_url(record.issue),
            "project_labels": labels,
            "ccb_no": values["ccb_no"],
            "due_date": values["due_date"].isoformat(),
            "record_id": str(record.id),
            "record_version": values["version"],
        },
    }


def reminder_recipients(subtasks):
    recipients = set()
    for subtask in subtasks:
        assignee = field(subtask.fields, "assignee")
        candidate = str(field(assignee, "emailAddress") or "").strip()
        if not candidate:
            continue
        try:
            validate_email(candidate)
        except DjangoValidationError:
            continue
        recipients.add(candidate.casefold())
    if len(recipients) > MAX_RECIPIENTS:
        raise ValidationError({"recipients": "The reminder has too many recipients."})
    return sorted(recipients)


def require_active_record(record):
    if not record.active:
        raise ValidationError({"record": "Only active DCC records can receive reminders."})


def require_current_version(record, expected_version):
    if record.version != expected_version:
        raise ValidationError({"version": "The DCC record changed; reload and retry."})


def verify_replay(delivery, record_id, values):
    context = delivery.context
    expected = {
        "record_id": str(record_id),
        "record_version": values["version"],
        "ccb_no": values["ccb_no"],
        "due_date": values["due_date"].isoformat(),
    }
    if any(context.get(key) != value for key, value in expected.items()):
        raise IdempotencyConflict()
