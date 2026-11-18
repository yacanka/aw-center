"""Project visible JIRA issue fields into plain text for published templates."""

import math
import re
from contextlib import closing
from datetime import date, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django.conf import settings
from jira import JIRAError
from requests.exceptions import RequestException
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from .sessions import jira_connector_for, jira_status_code
from .template_docx import INVALID_XML_CHAR, MAX_VALUE_LENGTH


ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9_]*-[1-9][0-9]*", re.ASCII | re.IGNORECASE)
ISTANBUL = ZoneInfo("Europe/Istanbul")
REFERENCE_LABELS = {
    "user": "displayName", "option": "value", "option-with-child": "value",
    "issue": "key", "parent": "key",
    "project": "name", "issuetype": "name", "priority": "name", "status": "name",
    "resolution": "name", "version": "name", "component": "name", "group": "name",
    "securitylevel": "name",
}
SYSTEM_TYPES = {
    "created": "datetime", "updated": "datetime", "resolutiondate": "datetime",
    "duedate": "date", "assignee": "user", "creator": "user", "reporter": "user",
    "subtasks": "issue", "components": "component", "versions": "version", "fixVersions": "version",
}


class TemplateIssueUnavailable(APIException):
    status_code = 502
    default_code = "JIRA_TEMPLATE_ISSUE_UNAVAILABLE"
    default_detail = "JIRA could not return a usable issue. Check the connection and try again."


class TemplateIssueSessionExpired(APIException):
    status_code = 409
    default_code = "JIRA_SESSION_REQUIRED"
    default_detail = "Reconnect your JIRA account and try again."


def _origin(url):
    port = url.port if url.port is not None else {"http": 80, "https": 443}.get(url.scheme)
    return url.scheme, url.hostname, port


def template_issue_key(reference):
    """Accept a key or a browse link under the configured JIRA installation."""

    value = reference.strip() if isinstance(reference, str) else ""
    invalid = ValidationError("Enter a valid JIRA issue key or configured browse URL.")
    if not value or len(value) > 2048 or any(ord(ch) < 32 for ch in value):
        raise invalid
    if not ISSUE_KEY.fullmatch(value):
        try:
            url, base = urlsplit(value), urlsplit(settings.JIRA_URL)
            prefix = base.path.rstrip("/") + "/browse/"
            if (_origin(url) != _origin(base) or url.username is not None or
                    url.password is not None or not url.path.startswith(prefix)):
                raise invalid
            value = url.path[len(prefix):]
        except ValueError:
            raise invalid from None
    if len(value) > 128 or not ISSUE_KEY.fullmatch(value):
        raise invalid
    return value.upper()


def read_template_issue(user, issue):
    """Fetch the issue as the current user, including names and schema for returned fields."""

    key = template_issue_key(issue)
    try:
        with closing(jira_connector_for(user).get_client()) as client:
            resource = client.issue(key, fields="*all", expand="names,schema")
    except JIRAError as error:
        status = jira_status_code(error)
        if status == 401:
            raise TemplateIssueSessionExpired() from None
        if status == 403:
            raise PermissionDenied("Your JIRA account cannot read this issue.") from None
        if status == 404:
            raise NotFound("The JIRA issue is unavailable.") from None
        raise TemplateIssueUnavailable() from None
    except RequestException:
        raise TemplateIssueUnavailable() from None
    return _project_issue(getattr(resource, "raw", None))


def _identity(fields, field_id):
    value = fields.get(field_id)
    if not isinstance(value, dict):
        raise TemplateIssueUnavailable()
    identifier, name = value.get("id"), value.get("name")
    if (not isinstance(identifier, (str, int)) or isinstance(identifier, bool)
            or not 0 < len(str(identifier)) <= 128 or not isinstance(name, str)
            or not name.strip() or len(name) > 255):
        raise TemplateIssueUnavailable()
    return str(identifier), name


def _project_issue(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("fields"), dict):
        raise TemplateIssueUnavailable()
    key = raw.get("key")
    if not isinstance(key, str) or len(key) > 128 or not ISSUE_KEY.fullmatch(key):
        raise TemplateIssueUnavailable()
    fields = raw["fields"]
    project_id, project_name = _identity(fields, "project")
    type_id, type_name = _identity(fields, "issuetype")
    names = raw.get("names") or {}
    schemas = raw.get("schema") or {}
    if not isinstance(names, dict) or not isinstance(schemas, dict):
        raise TemplateIssueUnavailable()
    rows = []
    total_size = 0
    for identifier, raw_value in {**fields, "key": key}.items():
        schema = schemas.get(identifier) or {}
        name = names.get(identifier) or ("Issue key" if identifier == "key" else identifier)
        if not isinstance(name, str) or not isinstance(schema, dict):
            raise TemplateIssueUnavailable()
        value = _field_text(raw_value, schema, identifier)
        if value is not None and (len(value) > MAX_VALUE_LENGTH or INVALID_XML_CHAR.search(value)):
            value = None
        total_size += len(name) + len(identifier) + len(value or "") + 64
        if total_size > settings.JOB_JSON_MAX_INPUT_BYTES:
            raise TemplateIssueUnavailable("The issue contains too much field text to process.")
        rows.append({"id": identifier, "name": name, "value": value or "", "supported": value is not None})
    return {"issue": key, "project_id": project_id, "project_name": project_name,
            "issue_type_id": type_id, "issue_type_name": type_name, "fields": rows}


# These collections contain structured records without a supported plain-text projection.
UNSUPPORTED_TYPES = frozenset({"attachment", "issuelink", "issuelinks", "comment", "comments", "worklog"})


def _field_text(value, schema, identifier):
    if any(isinstance(key, str) and key in UNSUPPORTED_TYPES
           for key in (identifier, schema.get("type"), schema.get("items"))):
        return None
    kind = schema.get("type") or SYSTEM_TYPES.get(identifier, identifier)
    if isinstance(value, list):
        item_type = schema.get("items") or kind
        items = [_scalar_text(item, item_type) for item in value]
        return None if None in items else "\n".join(items)
    return _scalar_text(value, kind)


def _scalar_text(value, kind):
    if not isinstance(kind, str):
        return None
    if value is None:
        return ""
    if isinstance(value, str):
        return _date_text(value, kind) if value and kind in {"date", "datetime"} else value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) or isinstance(value, float) and math.isfinite(value):
        return str(value)
    if not isinstance(value, dict):
        return None
    if value.get("type") == "doc":
        return _rich_text(value)
    label = value.get(REFERENCE_LABELS.get(kind))
    if not isinstance(label, str):
        return None
    if "child" in value and kind in {"option", "option-with-child"}:
        child = value.get("child")
        if child is not None:
            child_label = child.get("value") if isinstance(child, dict) else None
            return f"{label} / {child_label}" if isinstance(child_label, str) else None
    return label


def _date_text(value, kind):
    try:
        if kind == "date":
            return date.fromisoformat(value).strftime("%d.%m.%Y")
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(ISTANBUL)
        return timestamp.strftime("%d.%m.%Y %H:%M")
    except (ValueError, OverflowError):
        return None


def _rich_text(node, depth=0):
    """Retain paragraph boundaries and reject unsupported rich content as a whole."""

    if not isinstance(node, dict) or depth > 24:
        return None
    kind = node.get("type")
    if kind == "text":
        return node.get("text") if isinstance(node.get("text"), str) else None
    if kind == "hardBreak":
        return "\n"
    separators = {"doc": "\n", "paragraph": "", "heading": "", "codeBlock": "",
                  "blockquote": "\n", "bulletList": "\n", "orderedList": "\n", "listItem": "\n"}
    children = node.get("content", [])
    if not isinstance(kind, str) or kind not in separators or not isinstance(children, list):
        return None
    values = [_rich_text(child, depth + 1) for child in children]
    return None if None in values else separators[kind].join(values)
