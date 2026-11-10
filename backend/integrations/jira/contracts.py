"""Validation and sanitized error contracts shared by JIRA features."""

import math
import re

from rest_framework.exceptions import APIException, ValidationError

PROJECT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")
ISSUE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,19}-[1-9][0-9]*$")
FIELD_KEY_PATTERN = re.compile(r"^(?:customfield_[1-9][0-9]*|[a-z][a-z0-9_]{0,63})$")
MAX_EXTRA_FIELDS = 30
MAX_FIELD_TEXT_LENGTH = 2000


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


def validate_issue_key(value):
    """Reject malformed identifiers returned by the external system."""

    normalized = str(value or "").strip().upper()
    if not ISSUE_KEY_PATTERN.fullmatch(normalized):
        raise JiraDraftPublishFailure()
    return normalized


def validate_extra_fields(value):
    """Validate bounded scalars, references and lists without trusting field identifiers."""

    if not isinstance(value, dict) or len(value) > MAX_EXTRA_FIELDS:
        raise ValidationError("Use an object containing at most 30 JIRA fields.")
    return {validate_field_key(key): validate_field_value(item) for key, item in value.items()}


def validate_field_key(value):
    key = str(value or "")
    if not FIELD_KEY_PATTERN.fullmatch(key):
        raise ValidationError(f"Unsupported JIRA field identifier: {key[:64]}")
    return key


def validate_field_value(value):
    if isinstance(value, dict):
        return validate_reference(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return validate_scalar(value)
    if not isinstance(value, list) or len(value) > 50:
        raise ValidationError("JIRA field values must be scalars or lists of at most 50 values.")
    return [validate_reference(item) if isinstance(item, dict) else validate_scalar(item) for item in value]


def validate_scalar(value):
    if not isinstance(value, (str, int, float, bool, type(None))):
        raise ValidationError("JIRA field values cannot contain nested objects.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValidationError("JIRA numbers must be finite.")
    if isinstance(value, str) and len(value) > MAX_FIELD_TEXT_LENGTH:
        raise ValidationError("JIRA field text values cannot exceed 2000 characters.")
    return value


def validate_reference(value, *, child=False):
    """Accept bounded references, never arbitrary issue-response objects."""
    keys = {"id", "name", "key", "accountId", "value"}
    if not value or set(value) - (keys if child else keys | {"child"}):
        raise ValidationError("Use a JIRA reference identifier, not a full object.")
    result = {}
    for key, item in value.items():
        if key == "child":
            if not isinstance(item, dict):
                raise ValidationError("Use a child option reference.")
            result[key] = validate_reference(item, child=True)
        else:
            if isinstance(item, bool) or not isinstance(item, (str, int)) or not str(item).strip():
                raise ValidationError("Use a non-empty JIRA reference identifier.")
            result[key] = validate_scalar(item)
    if not set(result) & keys:
        raise ValidationError("A parent reference is required.")
    return result
