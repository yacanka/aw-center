"""Capture an immutable credential-free DCC source snapshot from JIRA."""

import json
import re

from orgs.models import Project

from .access_policy import OPERATOR, require_projects_role
from .document_fields import field, main_issue_fields, panel_fields
from .service.text_parsing import classify_dcc
from .services.project_resolver import resolve_projects_from_jira_components

ISSUE_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")
MAX_SUBTASKS = 200
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
SNAPSHOT_SCHEMA_VERSION = 2


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


def capture_dcc_snapshot(connector, issue_reference, actor):
    """Read JIRA once and return a bounded snapshot without persisting credentials."""

    issue_key = extract_issue_key(issue_reference)
    if not connector.current_user():
        raise DccSnapshotError("The JIRA session is not authenticated.", "DCC_SESSION_INVALID")
    connector.set_issue(issue_key)
    issue = connector.get_issue()
    validate_parent_issue(issue)
    definitions = resolve_projects_from_jira_components(field(issue.fields, "components"))
    if len(definitions) != 1:
        raise DccSnapshotError(
            "The JIRA task must identify exactly one DCC project.",
            "DCC_PROJECT_AMBIGUOUS",
        )
    projects = resolve_enabled_projects(definitions)
    require_projects_role(actor, projects, OPERATOR)
    snapshot = build_snapshot(connector, issue, issue_key, definitions, projects)
    validate_snapshot_size(snapshot)
    return snapshot


def validate_parent_issue(issue):
    """Reject missing issues and subtask sources before document generation."""

    if issue is None:
        raise DccSnapshotError("The JIRA task could not be found.", "DCC_ISSUE_NOT_FOUND")
    if field(field(issue.fields, "issuetype"), "subtask"):
        raise DccSnapshotError("Use a parent task instead of a subtask.", "DCC_SUBTASK_UNSUPPORTED")
    if len(field(issue.fields, "subtasks") or []) > MAX_SUBTASKS:
        raise DccSnapshotError("The task has too many subtasks to process safely.", "DCC_TOO_MANY_SUBTASKS")


def resolve_enabled_projects(definitions):
    slugs = [definition.slug for definition in definitions]
    projects_by_slug = {
        project.slug: project
        for project in Project.objects.filter(slug__in=slugs, enabled=True)
    }
    if set(projects_by_slug) != set(slugs):
        raise DccSnapshotError(
            "The JIRA task includes an unavailable project.",
            "DCC_PROJECT_INVALID",
        )
    return [projects_by_slug[slug] for slug in slugs]


def build_snapshot(connector, issue, issue_key, definitions, projects):
    """Build the versioned, JSON-serializable DCC rendering contract."""

    placeholders = main_issue_fields(issue.fields)
    primary = definitions[0]
    panels = fetch_panels(connector, issue)
    panel_values, classifications, responsible_values, panel_titles = build_panel_values(
        panels, primary
    )
    placeholders["Panels"] = panel_values
    apply_classification(placeholders, classifications)
    apply_responsible(placeholders, classifications, responsible_values)
    form_number = placeholders.get("DCC_Form_Number", issue_key)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "issue_key": issue_key,
        "project_slug": primary.slug,
        "project_slugs": [definition.slug for definition in definitions],
        "project_ids": [project.pk for project in projects],
        "project_label": primary.dcc_label or primary.jira_component or primary.slug,
        "output_name": safe_output_name(form_number),
        "panel_count": len(panels),
        "panel_titles": panel_titles,
        "placeholders": placeholders,
    }


def fetch_panels(connector, issue):
    """Fetch each bounded JIRA subtask once for project processing."""

    return tuple(
        connector.get_client().issue(subtask.key)
        for subtask in field(issue.fields, "subtasks") or []
    )


def build_panel_values(panels, project):
    """Build the ordered panel array consumed by the DOCX template."""

    panel_values, classifications, responsible_values, panel_titles = [], [], set(), []
    for panel in panels:
        values, classification, responsible = panel_fields(
            panel.fields, project.slug == "gokbey"
        )
        panel_values.append(values)
        classifications.append(classification)
        title = str(field(panel.fields, "summary") or "").strip()
        if title:
            panel_titles.append(title[:500])
        if responsible:
            responsible_values.add(responsible)
    return panel_values, classifications, responsible_values, panel_titles


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
    if responsible:
        raw_name = field(responsible, "displayName")
        if isinstance(raw_name, str) and raw_name.strip():
            placeholders["Responsible_AS"] = raw_name.split("(", 1)[0].strip()


def safe_output_name(form_number):
    """Return a bounded filename that cannot escape private job storage."""

    normalized = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(form_number)).strip(" ._")
    return f"{(normalized or 'DCC')[:140]}.docx"


def validate_snapshot_size(snapshot):
    """Reject oversized JIRA content instead of silently truncating compliance data."""

    size = len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))
    if size > MAX_SNAPSHOT_BYTES:
        raise DccSnapshotError("The JIRA task content is too large.", "DCC_SNAPSHOT_TOO_LARGE")
