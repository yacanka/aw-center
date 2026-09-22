"""Schema-driven JIRA validation and create-payload encoding.

Only documented reference shapes are emitted. Unknown object schemas fail closed;
values from issue responses must never be stringified into JIRA references.
"""

import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

RAW_TYPES = {"string", "date", "datetime", "number", "integer", "float", "double", "boolean"}
OBJECT_TYPES = {"user", "option", "priority", "component", "version", "group"}
REFERENCE_KEYS = ("id", "value", "name", "key", "accountId")


def build_extra_issue_fields(draft, metadata):
    fields = {field.get("id"): field for field in metadata if field.get("id")}
    return {
        identifier: encode_value(value, fields[identifier])
        for identifier, value in draft.extra_fields.items()
        if identifier in fields and has_value(value)
    }


def encode_value(value, field):
    schema = field.get("schema") or {}
    field_type = str(schema.get("type") or "").lower()
    if field_type == "option-with-child" or str(schema.get("custom") or "").endswith(":cascadingselect"):
        return encode_cascade(value, field)
    if field_type == "array":
        if not isinstance(value, list):
            raise ValueError("Use a list of values.")
        return [encode_scalar(item, str(schema.get("items") or "").lower(), field) for item in value]
    if isinstance(value, list):
        raise ValueError("Use a single value.")
    return encode_scalar(value, field_type, field)


def encode_scalar(value, field_type, field):
    if field_type in {"number", "integer", "float", "double"}:
        return encode_number(value, field_type)
    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            return value.strip().lower() == "true"
        raise ValueError("Use true or false.")
    if field_type in {"date", "datetime"}:
        return encode_date(value, field_type)
    if isinstance(value, dict) and "child" in value:
        raise ValueError("Child options require a cascading select field.")
    allowed = field.get("allowedValues") or []
    matched = match_allowed(value, allowed) if allowed else None
    if allowed and matched is None:
        raise ValueError("Choose a unique available option.")
    if field_type == "string":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Use non-empty text.")
        return value
    if field_type not in OBJECT_TYPES:
        raise ValueError("This JIRA field type is not supported.")
    if matched is not None:
        return object_reference(matched, field_type)
    if isinstance(value, dict):
        return object_reference(value, field_type)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Use an option or user identifier.")
    key = "value" if field_type == "option" else "name"
    return {key: value.strip()}


def encode_number(value, field_type):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Use a finite number.")
    if isinstance(value, int):
        return value
    try:
        decimal = Decimal(str(value))
        number = float(decimal)
    except (InvalidOperation, ValueError, OverflowError) as error:
        raise ValueError("Use a finite number.") from error
    if not math.isfinite(number):
        raise ValueError("Use a finite number.")
    if field_type == "integer" and decimal != decimal.to_integral_value():
        raise ValueError("Use a whole number.")
    return int(decimal) if decimal == decimal.to_integral_value() else number


def encode_date(value, field_type):
    if not isinstance(value, str):
        raise ValueError("Use an ISO date.")
    if field_type == "date":
        if len(value) != 10:
            raise ValueError("Use YYYY-MM-DD.")
        return date.fromisoformat(value).isoformat()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if "T" not in value or parsed.utcoffset() is None:
        raise ValueError("Include the time and timezone.")
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + parsed.strftime("%z")


def encode_cascade(value, field):
    parent_value = {key: item for key, item in value.items() if key != "child"} if isinstance(value, dict) else value
    parent = match_allowed(parent_value, field.get("allowedValues") or [])
    if parent is None:
        raise ValueError("Choose an available parent option.")
    result = object_reference(parent, "option")
    if isinstance(value, dict) and has_value(value.get("child")):
        child = match_allowed(value["child"], parent.get("children") or [])
        if child is None:
            raise ValueError("Choose a child belonging to the selected parent.")
        result["child"] = object_reference(child, "option")
    return result


def object_reference(item, field_type):
    keys = ("accountId", "name", "key") if field_type == "user" else ("name",) if field_type == "group" else ("id", "value", "name", "key")
    key = next((key for key in keys if isinstance(item.get(key), (str, int)) and not isinstance(item[key], bool) and str(item[key]).strip()), None)
    if key is None:
        raise ValueError("The object has no usable JIRA identifier.")
    return {key: str(item[key])}


def match_allowed(value, allowed):
    candidates = [item for item in allowed if isinstance(item, dict) and not item.get("disabled")]
    if isinstance(value, dict):
        keys = [key for key in REFERENCE_KEYS if has_value(value.get(key))]
        # Stable identifiers take precedence over mutable display labels.
        key = next((key for key in ("id", "accountId", "key") if key in keys), None)
        keys = [key] if key else keys
        matches = [item for item in candidates if keys and all(str(item.get(key)) == str(value[key]) for key in keys)]
    else:
        token = str(value)
        exact = [item for item in candidates if token in {str(item[key]) for key in ("id", "accountId", "key") if item.get(key) is not None}]
        matches = exact or [item for item in candidates if token in option_identifiers(item)]
    return matches[0] if len(matches) == 1 else None


def option_identifiers(item):
    return {str(item[key]) for key in REFERENCE_KEYS if item.get(key) is not None}


def option_token(item):
    token = next((item[key] for key in REFERENCE_KEYS if item.get(key) is not None), None)
    return safe_text(token, 200) if isinstance(token, (str, int, float)) else None


def option_label(item):
    keys = ("value", "displayName", "name", "key", "id")
    return next((str(item[key]) for key in keys if item.get(key) is not None), "Unknown")


def safe_text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def has_value(value):
    return value is not None and value != "" and value != []
