"""Safe JIRA draft value matching and create-payload encoding."""

RAW_TYPES = {"string", "date", "datetime", "number", "integer", "float", "double"}


def build_extra_issue_fields(draft, metadata):
    """Encode only live create-screen fields; stale saved identifiers are ignored."""
    fields = {field.get("id"): field for field in metadata if field.get("id")}
    return {
        identifier: encode_value(value, fields[identifier])
        for identifier, value in draft.extra_fields.items()
        if identifier in fields and has_value(value)
    }


def encode_value(value, field):
    """Encode one scalar or array according to its live JIRA schema."""
    schema = field.get("schema") or {}
    item_type = str(schema.get("items") or schema.get("type") or "").lower()
    if isinstance(value, list):
        return [encode_scalar(item, item_type, field) for item in value]
    return encode_scalar(value, item_type, field)


def encode_scalar(value, field_type, field):
    """Encode raw scalars directly and reference-like fields as JIRA objects."""
    if field_type in RAW_TYPES:
        return value
    matched = match_allowed(value, field.get("allowedValues") or [])
    if matched:
        return object_reference(matched, field_type)
    return {"name": str(value)} if field_type != "option" else {"value": str(value)}


def object_reference(item, field_type):
    """Return the least ambiguous identifier accepted by JIRA Server objects."""
    if field_type == "user":
        key = next((key for key in ("name", "key", "accountId") if item.get(key)), None)
    else:
        key = next((key for key in ("id", "value", "name", "key") if item.get(key)), None)
    return {key: item[key]} if key else {"name": option_label(item)}


def match_allowed(value, allowed):
    """Find an allowed option by its stable id, value, name, or key."""
    token = str(value)
    return next(
        (item for item in allowed if isinstance(item, dict) and token in option_identifiers(item)),
        None,
    )


def option_identifiers(item):
    """Return comparable non-empty identifiers for one JIRA option."""
    keys = ("id", "value", "name", "key", "accountId")
    return {str(item[key]) for key in keys if item.get(key) is not None}


def option_token(item):
    """Choose a stable primitive token for browser storage."""
    keys = ("id", "value", "name", "key", "accountId")
    token = next((item[key] for key in keys if item.get(key) is not None), None)
    return safe_text(token, 200) if isinstance(token, (str, int, float)) else None


def option_label(item):
    """Choose a human-readable option label."""
    keys = ("value", "name", "displayName", "key", "id")
    return next((str(item[key]) for key in keys if item.get(key) is not None), "Unknown")


def safe_text(value, limit):
    """Normalize untrusted metadata to one bounded display line."""
    return " ".join(str(value or "").split())[:limit]


def has_value(value):
    """Treat zero as present while rejecting empty strings and collections."""
    return value is not None and value != "" and value != []
