"""Sanitized JIRA create-contract preflight for human-approved issue drafts."""

from datetime import date, datetime

from .issue_draft_contracts import FIELD_KEY_PATTERN, JiraDraftPreflightBlocked
from .issue_draft_field_values import (
    has_value, match_allowed, option_label, option_token, safe_text,
)

BASE_FIELDS = {"project", "summary", "description", "issuetype", "labels"}
REQUIRED_SCREEN_FIELDS = {"summary", "description", "labels"}
RAW_TYPES = {"string", "date", "datetime", "number", "integer", "float", "double"}
OBJECT_TYPES = {"user", "option", "priority", "component", "version"}
SUPPORTED_ARRAY_ITEMS = RAW_TYPES | OBJECT_TYPES


def inspect_create_contract(draft, client):
    """Return a content-safe view of live JIRA Task create requirements."""
    metadata = client.get_create_fields(draft.project_key, "Task")
    field_map = {field.get("id"): field for field in metadata if field.get("id")}
    required = required_extra_fields(field_map)
    supported = [field for field in required if field_supported(field)]
    result = {
        "ready": False,
        "project_key": draft.project_key,
        "issue_type": "Task",
        "fields": [public_field(field) for field in supported],
        "missing_fields": missing_fields(draft.extra_fields, supported),
        "invalid_fields": invalid_fields(draft.extra_fields, supported),
        "unsupported_fields": unsupported_fields(field_map, required),
        "warnings": stale_value_warnings(draft.extra_fields, field_map),
    }
    result["ready"] = not any(result[key] for key in blocker_keys())
    return result, metadata


def blocker_keys():
    """Return response collections that prevent a safe create call."""
    return ("missing_fields", "invalid_fields", "unsupported_fields")


def ensure_contract_ready(result):
    """Raise a structured client error when live requirements are incomplete."""
    if not result["ready"]:
        raise JiraDraftPreflightBlocked(result)


def required_extra_fields(field_map):
    """Return required non-base fields without a JIRA-provided default."""
    return [
        field for identifier, field in field_map.items()
        if identifier not in BASE_FIELDS and field.get("required")
        and not field.get("hasDefaultValue")
    ]


def unsupported_fields(field_map, required):
    """Describe absent safety fields and required types AW Center cannot encode."""
    blockers = [
        safe_identity(field_id, field_id)
        for field_id in REQUIRED_SCREEN_FIELDS - field_map.keys()
    ]
    blockers.extend(safe_identity(field.get("id"), field.get("name")) for field in required if not field_supported(field))
    return sorted(blockers, key=lambda item: item["name"])


def missing_fields(values, fields):
    """Describe supported required fields that do not yet have a draft value."""
    return [safe_identity(field["id"], field.get("name")) for field in fields if not has_value(values.get(field["id"]))]


def invalid_fields(values, fields):
    """Describe values that conflict with the current live field contract."""
    return [
        safe_identity(field["id"], field.get("name")) for field in fields
        if has_value(values.get(field["id"])) and not value_supported(values[field["id"]], field)
    ]


def stale_value_warnings(values, field_map):
    """Report saved values no longer present on the active create screen."""
    stale = sorted(set(values) - set(field_map))
    return [f"Saved field {identifier} is no longer on the JIRA create screen and will be ignored." for identifier in stale]


def field_supported(field):
    """Return whether AW Center can safely encode the field schema."""
    if not FIELD_KEY_PATTERN.fullmatch(str(field.get("id") or "")):
        return False
    schema = field.get("schema") or {}
    field_type = str(schema.get("type") or "").lower()
    if field_type in RAW_TYPES | OBJECT_TYPES:
        return True
    return field_type == "array" and str(schema.get("items") or "").lower() in SUPPORTED_ARRAY_ITEMS


def value_supported(value, field):
    """Validate shape and allowed-value membership against live metadata."""
    schema_type = str((field.get("schema") or {}).get("type") or "").lower()
    value_type = str((field.get("schema") or {}).get("items") or schema_type).lower()
    values = value if isinstance(value, list) else [value]
    if (schema_type == "array") != isinstance(value, list):
        return False
    if value_type in {"number", "integer", "float", "double"}:
        return all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in values)
    if value_type == "date":
        return all(valid_date(item) for item in values)
    if value_type == "datetime":
        return all(valid_datetime(item) for item in values)
    allowed = field.get("allowedValues") or []
    if allowed:
        return all(match_allowed(item, allowed) is not None for item in values)
    return all(isinstance(item, str) and bool(item.strip()) for item in values)


def valid_date(value):
    """Return whether a primitive is an actual ISO calendar date."""
    try:
        date.fromisoformat(value)
        return isinstance(value, str) and len(value) == 10
    except (TypeError, ValueError):
        return False


def valid_datetime(value):
    """Return whether a primitive is a parseable ISO timestamp."""
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return isinstance(value, str) and "T" in value
    except (AttributeError, TypeError, ValueError):
        return False


def public_field(field):
    """Reduce raw createmeta to the bounded browser contract."""
    schema = field.get("schema") or {}
    return {
        **safe_identity(field.get("id"), field.get("name")),
        "required": True,
        "schema": {"type": safe_text(schema.get("type"), 24), "items": safe_text(schema.get("items"), 24)},
        "allowedValues": public_options(field.get("allowedValues") or []),
    }


def public_options(values):
    """Return at most one hundred harmless option labels and stable tokens."""
    options = []
    for item in values[:100]:
        if not isinstance(item, dict):
            continue
        token = option_token(item)
        if token is not None:
            options.append({"label": safe_text(option_label(item), 100), "value": token})
    return options


def safe_identity(identifier, name):
    """Return a bounded field identity safe for browser display and logs."""
    return {"id": safe_text(identifier, 64), "name": safe_text(name or identifier, 100)}
