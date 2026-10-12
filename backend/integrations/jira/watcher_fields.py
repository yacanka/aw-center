"""Bounded display projections of fields available on one authorized JIRA task."""

import re

from .document_fields import field

MAX_DETAIL_FIELDS = 200
MAX_DISPLAY_CHARACTERS = 2000
STANDARD_LABELS = {
    "summary": "Title", "description": "Description", "status": "Status",
    "priority": "Priority", "issuetype": "Issue type", "resolution": "Resolution",
    "assignee": "Assignee", "reporter": "Reporter", "created": "Created",
    "updated": "Updated", "duedate": "Due date", "labels": "Labels",
    "components": "Components", "fixVersions": "Fix versions", "versions": "Versions",
}
DEFAULT_LABELS = {
    "customfield_45000": "ECD number", "customfield_45001": "Revision",
    "customfield_45002": "DCC number",
}


def is_detail_field_id(value):
    return isinstance(value, str) and (
        value in STANDARD_LABELS or re.fullmatch(r"customfield_[0-9]{1,12}", value) is not None
    )


def display_value(value, depth=0):
    """Project scalars and known option labels; never expose raw objects or URLs."""
    if value is None or depth > 3:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)[:MAX_DISPLAY_CHARACTERS]
    if isinstance(value, (list, tuple)):
        return ", ".join(filter(None, (display_value(item, depth + 1) for item in value[:50])))[
            :MAX_DISPLAY_CHARACTERS]
    for attribute in ("displayName", "value", "name"):
        label = field(value, attribute)
        if label is not None:
            return display_value(label, depth + 1)
    return ""


def issue_detail_fields(issue):
    raw_fields = field(field(issue, "raw"), "fields")
    fields = raw_fields if isinstance(raw_fields, dict) else field(issue, "fields")
    values = fields if isinstance(fields, dict) else vars(fields) if fields is not None else {}
    names = field(issue, "names") or field(field(issue, "raw"), "names") or {}
    if not isinstance(names, dict):
        names = {}
    keys = list(DEFAULT_LABELS) + [key for key in sorted(values) if key not in DEFAULT_LABELS]
    return [
        {"id": key, "label": display_value(names.get(key) or DEFAULT_LABELS.get(key)
                                          or STANDARD_LABELS.get(key) or key)[:255],
         "value": display_value(field(fields, key))}
        for key in keys if is_detail_field_id(key)
    ][:MAX_DETAIL_FIELDS]
