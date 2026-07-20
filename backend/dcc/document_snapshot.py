"""Capture an immutable credential-free DCC source snapshot from JIRA."""

import json
import re

from .document_fields import field, main_issue_fields, panel_fields
from .service.JIRAConnector import JiraConnector
from .service.text_parsing import classify_dcc
from .services.project_resolver import resolve_project_from_jira_components

ISSUE_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")
MAX_SUBTASKS = 200
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024


class DccSnapshotError(ValueError):
    """Represent a safe, actionable DCC source validation failure."""

    def __init__(self, message, code, response_status=400):
        super().__init__(message)
        self.code = code
        self.response_status = response_status


def extract_issue_key(issue_reference):
    """Extract a canonical JIRA issue key from a key or browse URL."""

    normalized = str(issue_reference or "").strip().upper()
    match = ISSUE_PATTERN.search(normalized)
    if not match:
        raise DccSnapshotError("Enter a valid JIRA task URL or issue key.", "DCC_ISSUE_INVALID")
    return match.group(0)


def capture_dcc_snapshot(session_id, issue_reference, server_url):
    """Read JIRA once and return a bounded snapshot without persisting credentials."""

    issue_key = extract_issue_key(issue_reference)
    connector = authenticated_connector(session_id, server_url)
    connector.set_issue(issue_key)
    issue = connector.get_issue()
    validate_parent_issue(issue)
    project = resolve_project_from_jira_components(field(issue.fields, "components"))
    snapshot = build_snapshot(connector, issue, issue_key, project)
    validate_snapshot_size(snapshot)
    return snapshot


def authenticated_connector(session_id, server_url):
    """Create a JIRA connector and verify the transient session immediately."""

    connector = JiraConnector(server_url=server_url, jira_session_id=session_id)
    if not connector.get_client().myself():
        raise DccSnapshotError("The JIRA session is not authenticated.", "DCC_SESSION_INVALID")
    return connector


def validate_parent_issue(issue):
    """Reject missing issues and subtask sources before document generation."""

    if issue is None:
        raise DccSnapshotError("The JIRA task could not be found.", "DCC_ISSUE_NOT_FOUND")
    if field(field(issue.fields, "issuetype"), "subtask"):
        raise DccSnapshotError("Use a parent task instead of a subtask.", "DCC_SUBTASK_UNSUPPORTED")
    if len(field(issue.fields, "subtasks") or []) > MAX_SUBTASKS:
        raise DccSnapshotError("The task has too many subtasks to process safely.", "DCC_TOO_MANY_SUBTASKS")


def build_snapshot(connector, issue, issue_key, project):
    """Build the versioned, JSON-serializable DCC rendering contract."""

    placeholders = main_issue_fields(issue.fields)
    classifications, responsible_values, panel_titles = append_panels(
        connector, issue, project, placeholders
    )
    apply_classification(placeholders, classifications)
    apply_responsible(placeholders, classifications, responsible_values)
    form_number = placeholders.get("DCC_Form_Number", issue_key)
    return {
        "schema_version": 1,
        "issue_key": issue_key,
        "project_slug": project.slug,
        "project_label": project.display_name or project.jira_component,
        "output_name": safe_output_name(form_number),
        "panel_count": len(field(issue.fields, "subtasks") or []),
        "panel_titles": panel_titles,
        "placeholders": placeholders,
    }


def append_panels(connector, issue, project, placeholders):
    """Fetch subtask snapshots and merge their template fields."""

    classifications, responsible_values, panel_titles = [], set(), []
    for index, subtask in enumerate(field(issue.fields, "subtasks") or []):
        panel = connector.get_client().issue(subtask.key)
        values, classification, responsible = panel_fields(
            panel.fields, index, project.slug == "gokbey"
        )
        placeholders.update(values)
        classifications.append(classification)
        title = str(field(panel.fields, "summary") or "").strip()
        if title:
            panel_titles.append(title[:500])
        if responsible:
            responsible_values.add(responsible)
    return classifications, responsible_values, panel_titles


def apply_classification(placeholders, classifications):
    """Fill classification from panels only when the parent did not provide one."""

    classified_type, _responsible = classify_dcc(classifications)
    if classified_type and not placeholders.get("Design_Change_Classification"):
        placeholders["Design_Change_Classification"] = classified_type


def apply_responsible(placeholders, classifications, responsible_values):
    """Resolve one responsible AS or reject conflicting explicit JIRA values."""

    if len(responsible_values) > 1:
        raise DccSnapshotError(
            "Panel subtasks contain conflicting Responsible AS values.", "DCC_RESPONSIBLE_CONFLICT"
        )
    if responsible_values:
        placeholders["Responsible_AS"] = next(iter(responsible_values))
        return
    _classified_type, responsible = classify_dcc(classifications)
    from .document_fields import display_name

    if responsible:
        placeholders["Responsible_AS"] = display_name(responsible)


def safe_output_name(form_number):
    """Return a bounded filename that cannot escape private job storage."""

    normalized = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(form_number)).strip(" ._")
    return f"{(normalized or 'DCC')[:140]}.docx"


def validate_snapshot_size(snapshot):
    """Reject oversized JIRA content instead of silently truncating compliance data."""

    size = len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))
    if size > MAX_SNAPSHOT_BYTES:
        raise DccSnapshotError("The JIRA task content is too large.", "DCC_SNAPSHOT_TOO_LARGE")
