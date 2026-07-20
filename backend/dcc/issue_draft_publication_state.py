"""Transactional publication state transitions for JIRA issue drafts."""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .issue_draft_contracts import DraftStateConflict, validate_version
from .issue_draft_models import JiraIssueDraft, JiraIssueDraftEvent, JiraIssueDraftStatus


def reserve_publication(draft_id, owner, expected_version):
    """Reserve one external side effect after validating state and version."""
    with transaction.atomic():
        draft = lock_owned_draft(draft_id, owner)
        if draft.status == JiraIssueDraftStatus.PUBLISHED:
            return draft
        validate_version(draft.version, expected_version)
        if not publication_allowed(draft):
            raise DraftStateConflict()
        draft.status = JiraIssueDraftStatus.PUBLISHING
        draft.publish_started_at = timezone.now()
        clear_failure(draft)
        draft.version += 1
        draft.save()
        record_event(draft, owner, "publication_started")
    return draft


def publication_allowed(draft):
    """Allow approved/failed drafts and stale interrupted reservations."""
    if draft.status in {JiraIssueDraftStatus.APPROVED, JiraIssueDraftStatus.FAILED}:
        return bool(draft.approved_at)
    if draft.status != JiraIssueDraftStatus.PUBLISHING or not draft.publish_started_at:
        return False
    stale_seconds = max(60, int(settings.JIRA_DRAFT_PUBLISH_STALE_SECONDS))
    stale_at = timezone.now() - timedelta(seconds=stale_seconds)
    return draft.publish_started_at <= stale_at


def complete_publication(draft_id, actor, issue_key):
    """Persist the confirmed JIRA identifier after the external call succeeds."""
    with transaction.atomic():
        draft = JiraIssueDraft.objects.select_for_update().get(pk=draft_id)
        if draft.status == JiraIssueDraftStatus.PUBLISHED:
            return draft
        if draft.status != JiraIssueDraftStatus.PUBLISHING:
            raise DraftStateConflict()
        draft.status = JiraIssueDraftStatus.PUBLISHED
        draft.jira_issue_key = issue_key
        draft.published_by = actor
        draft.published_at = timezone.now()
        draft.version += 1
        draft.save()
        record_event(draft, actor, "published", {"jira_issue_key": issue_key})
    return draft


def mark_publication_blocked(draft_id, actor):
    """Restore approval after a no-write live contract blocker."""
    with transaction.atomic():
        draft = JiraIssueDraft.objects.select_for_update().get(pk=draft_id)
        if draft.status != JiraIssueDraftStatus.PUBLISHING:
            return
        draft.status = JiraIssueDraftStatus.APPROVED
        draft.last_error_code = "JIRA_DRAFT_PREFLIGHT_BLOCKED"
        draft.last_error_message = "Complete the required JIRA fields before publication."
        draft.version += 1
        draft.save()
        record_event(draft, actor, "publication_blocked", {"code": draft.last_error_code})


def mark_publication_failed(draft_id, actor):
    """Return an interrupted publication to a retryable, sanitized state."""
    with transaction.atomic():
        draft = JiraIssueDraft.objects.select_for_update().get(pk=draft_id)
        if draft.status != JiraIssueDraftStatus.PUBLISHING:
            return
        draft.status = JiraIssueDraftStatus.FAILED
        draft.last_error_code = "JIRA_DRAFT_PUBLISH_FAILED"
        draft.last_error_message = "JIRA did not confirm issue publication."
        draft.version += 1
        draft.save()
        record_event(draft, actor, "publication_failed", {"code": draft.last_error_code})


def lock_owned_draft(draft_id, owner):
    """Lock one owner-scoped publication target."""
    return JiraIssueDraft.objects.select_for_update().get(pk=draft_id, owner=owner)


def clear_failure(draft):
    """Clear safe failure metadata before another publication attempt."""
    draft.last_error_code = ""
    draft.last_error_message = ""


def record_event(draft, actor, event_type, details=None):
    """Append a content-free publication audit event."""
    return JiraIssueDraftEvent.objects.create(
        draft=draft, actor=actor, event_type=event_type,
        version=draft.version, details=details or {},
    )
