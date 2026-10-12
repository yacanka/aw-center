"""Optimistic-concurrency contracts owned by reviewable DCC drafts."""

from rest_framework.exceptions import APIException


class DraftVersionConflict(APIException):
    """Reject stale optimistic-concurrency writes."""

    status_code = 409
    default_code = "JIRA_DRAFT_VERSION_CONFLICT"
    default_detail = "The draft changed. Refresh it before continuing."


class DraftStateConflict(APIException):
    """Reject lifecycle transitions from an incompatible state."""

    status_code = 409
    default_code = "JIRA_DRAFT_STATE_CONFLICT"
    default_detail = "The draft is not in a state that accepts this action."


def validate_version(actual, expected):
    """Reject a write based on stale client state."""

    if actual != expected:
        raise DraftVersionConflict()
