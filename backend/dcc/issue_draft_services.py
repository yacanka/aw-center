"""Transactional lifecycle services for reviewable JIRA issue drafts."""

import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone
from .issue_draft_builder import build_draft_content
from .issue_draft_contracts import (
    DraftStateConflict, JiraDraftPreflightBlocked, JiraDraftPublishFailure,
    normalize_project_key, validate_version,
)
from .issue_draft_models import JiraIssueDraft, JiraIssueDraftEvent, JiraIssueDraftStatus
from .issue_draft_publication_state import (
    complete_publication, mark_publication_blocked, mark_publication_failed,
    reserve_publication,
)
from .issue_draft_publisher import publish_to_jira


def create_issue_draft(owner, source_job, project_key):
    """Create or replay the single owned draft for a verified analysis job."""

    existing = JiraIssueDraft.objects.filter(owner=owner, source_job=source_job).first()
    if existing:
        return existing, False
    summary, description = build_draft_content(source_job)
    fields = draft_fields(owner, source_job, project_key, summary, description)
    try:
        with transaction.atomic():
            draft = JiraIssueDraft.objects.create(**fields)
            record_event(draft, owner, "created")
        return draft, True
    except IntegrityError:
        return JiraIssueDraft.objects.get(owner=owner, source_job=source_job), False


def draft_fields(owner, source_job, project_key, summary, description):
    """Return normalized fields including a server-controlled recovery marker."""

    draft_id = uuid.uuid4()
    return {
        "id": draft_id,
        "owner": owner,
        "source_job": source_job,
        "project_key": normalize_project_key(project_key),
        "summary": summary,
        "description": description,
        "marker_label": f"aw-center-{draft_id.hex}",
    }


def update_issue_draft(draft_id, owner, values, expected_version):
    """Apply a version-checked edit and invalidate any prior approval."""

    with transaction.atomic():
        draft = lock_owned_draft(draft_id, owner)
        validate_version(draft.version, expected_version)
        ensure_editable(draft)
        apply_edit(draft, values)
        record_event(draft, owner, "updated")
    return draft


def apply_edit(draft, values):
    """Persist normalized fields and reset the review decision."""

    draft.project_key = normalize_project_key(values["project_key"])
    draft.summary = values["summary"].strip()
    draft.description = values["description"].strip()
    draft.extra_fields = values.get("extra_fields", {})
    draft.status = JiraIssueDraftStatus.DRAFT
    draft.approved_by = None
    draft.approved_at = None
    clear_failure(draft)
    draft.version += 1
    draft.save()


def approve_issue_draft(draft_id, owner, expected_version):
    """Record an explicit human approval for the current immutable version."""

    with transaction.atomic():
        draft = lock_owned_draft(draft_id, owner)
        validate_version(draft.version, expected_version)
        if draft.status != JiraIssueDraftStatus.DRAFT:
            raise DraftStateConflict()
        draft.status = JiraIssueDraftStatus.APPROVED
        draft.approved_by = owner
        draft.approved_at = timezone.now()
        draft.version += 1
        draft.save()
        record_event(draft, owner, "approved")
    return draft


def publish_issue_draft(draft_id, owner, session_id, expected_version):
    """Publish an approved draft with crash-safe marker-based duplicate recovery."""

    draft = reserve_publication(draft_id, owner, expected_version)
    if draft.status == JiraIssueDraftStatus.PUBLISHED:
        return draft
    try:
        issue_key = publish_to_jira(draft, session_id)
    except JiraDraftPreflightBlocked:
        mark_publication_blocked(draft.id, owner)
        raise
    except Exception as error:
        mark_publication_failed(draft.id, owner)
        raise JiraDraftPublishFailure() from error
    return complete_publication(draft.id, owner, issue_key)


def lock_owned_draft(draft_id, owner):
    """Lock one owner-scoped draft or expose a non-enumerable not-found result."""

    return JiraIssueDraft.objects.select_for_update().get(pk=draft_id, owner=owner)


def ensure_editable(draft):
    """Protect in-flight and completed external records from mutation."""

    if draft.status in {JiraIssueDraftStatus.PUBLISHING, JiraIssueDraftStatus.PUBLISHED}:
        raise DraftStateConflict()


def clear_failure(draft):
    """Clear stale safe failure metadata before the next lifecycle step."""

    draft.last_error_code = ""
    draft.last_error_message = ""


def record_event(draft, actor, event_type, details=None):
    """Append a content-free immutable audit event."""

    return JiraIssueDraftEvent.objects.create(
        draft=draft, actor=actor, event_type=event_type,
        version=draft.version, details=details or {},
    )
