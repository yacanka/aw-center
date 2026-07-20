"""Validation and error contracts for reviewable JIRA issue drafts."""

import re

from rest_framework.exceptions import APIException, ValidationError

PROJECT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")
ISSUE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,19}-[1-9][0-9]*$")
FIELD_KEY_PATTERN = re.compile(r"^(?:customfield_[1-9][0-9]*|[a-z][a-z0-9_]{0,63})$")
MAX_EXTRA_FIELDS = 30
MAX_FIELD_TEXT_LENGTH = 2000


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


class JiraDraftPublishFailure(APIException):
    """Expose a sanitized external publication failure."""

    status_code = 502
    default_code = "JIRA_DRAFT_PUBLISH_FAILED"
    default_detail = "JIRA did not confirm issue publication. The draft is safe to retry."


class JiraDraftPreflightBlocked(APIException):
    """Reject publication when the live JIRA create contract is incomplete."""

    status_code = 422
    default_code = "JIRA_DRAFT_PREFLIGHT_BLOCKED"

    def __init__(self, result):
        """Expose only sanitized blocker identifiers and display names."""

        detail = {
            "detail": "Complete the required JIRA fields before publication.",
            "code": self.default_code,
            "errors": {
                "missing_fields": result["missing_fields"],
                "invalid_fields": result["invalid_fields"],
                "unsupported_fields": result["unsupported_fields"],
            },
        }
        super().__init__(detail)


class JiraDraftPreflightUnavailable(APIException):
    """Expose a sanitized failure to inspect the live JIRA create contract."""

    status_code = 502
    default_code = "JIRA_DRAFT_PREFLIGHT_UNAVAILABLE"
    default_detail = "JIRA create requirements could not be inspected. Verify the session and retry."


def normalize_project_key(value):
    """Return a validated uppercase JIRA project key."""

    normalized = str(value or "").strip().upper()
    if not PROJECT_KEY_PATTERN.fullmatch(normalized):
        raise ValidationError({"project_key": "Use a valid 2-20 character JIRA project key."})
    return normalized


def validate_version(actual, expected):
    """Reject a write based on stale client state."""

    if actual != expected:
        raise DraftVersionConflict()


def validate_issue_key(value):
    """Reject malformed identifiers returned by the external system."""

    normalized = str(value or "").strip().upper()
    if not ISSUE_KEY_PATTERN.fullmatch(normalized):
        raise JiraDraftPublishFailure()
    return normalized


def validate_session_id(value):
    """Require a bounded non-persistent JIRA session credential."""

    session_id = str(value or "").strip()
    if not 8 <= len(session_id) <= 4096 or any(character.isspace() for character in session_id):
        raise ValidationError({"JSESSIONID": "Enter a valid JIRA session ID."})
    return session_id


def validate_extra_fields(value):
    """Validate bounded scalar/list draft values without trusting JIRA field identifiers."""

    if not isinstance(value, dict) or len(value) > MAX_EXTRA_FIELDS:
        raise ValidationError("Use an object containing at most 30 JIRA fields.")
    return {validate_field_key(key): validate_field_value(item) for key, item in value.items()}


def validate_field_key(value):
    """Accept only bounded system or custom JIRA field identifiers."""

    key = str(value or "")
    if not FIELD_KEY_PATTERN.fullmatch(key):
        raise ValidationError(f"Unsupported JIRA field identifier: {key[:64]}")
    return key


def validate_field_value(value):
    """Accept only bounded JSON scalar values or short scalar lists."""

    if value is None or isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return validate_scalar(value)
    if not isinstance(value, list) or len(value) > 50:
        raise ValidationError("JIRA field values must be scalars or lists of at most 50 values.")
    return [validate_scalar(item) for item in value]


def validate_scalar(value):
    """Reject nested values and excessively large strings."""

    if isinstance(value, bool) or not isinstance(value, (str, int, float, type(None))):
        raise ValidationError("JIRA field values cannot contain nested objects.")
    if isinstance(value, str) and len(value) > MAX_FIELD_TEXT_LENGTH:
        raise ValidationError("JIRA field text values cannot exceed 2000 characters.")
    return value
