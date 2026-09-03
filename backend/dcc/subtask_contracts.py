"""Shared validation and JIRA inspection helpers for subtask workflows."""

from orgs.models import Project

from integrations.jira.create_contract import field_supported, value_supported
from integrations.jira.field_values import option_label, option_token
from integrations.jira.sessions import jira_connector_for

from .access_policy import OPERATOR, require_projects_role
from .document_fields import field
from .document_snapshot import extract_issue_key, validate_parent_issue
from .document_snapshot import DccSnapshotError
from .services.project_resolver import DccProjectResolutionError, resolve_projects_from_jira_components

RESERVED_METADATA_FIELDS = frozenset(
    {"project", "parent", "issuetype", "summary", "description", "assignee", "duedate", "labels"}
)
MAX_METADATA_FIELDS = 100
MAX_ALLOWED_VALUES = 100


def inspect_subtask_target(actor, issue_reference):
    """Resolve one authorized parent issue and its bounded create metadata."""

    connector = jira_connector_for(actor)
    issue_key = extract_issue_key(issue_reference)
    connector.set_issue(issue_key)
    issue = connector.get_issue()
    validate_parent_issue(issue)
    try:
        definitions = resolve_projects_from_jira_components(field(issue.fields, "components"))
    except DccProjectResolutionError as error:
        raise DccSnapshotError(
            "The JIRA task does not identify a supported DCC project.",
            "DCC_PROJECT_INVALID",
        ) from error
    project_slugs = [definition.slug for definition in definitions]
    projects = list(
        Project.objects.filter(slug__in=project_slugs, enabled=True).order_by("pk")
    )
    if {project.slug for project in projects} != set(project_slugs):
        raise DccSnapshotError(
            "The JIRA task includes an unavailable project.",
            "DCC_PROJECT_INVALID",
        )
    require_projects_role(actor, projects, OPERATOR)
    metadata = sanitize_subtask_fields(connector.get_subtask_fields())
    return connector, issue_key, projects, metadata


def sanitize_subtask_fields(fields):
    """Return only bounded metadata needed to render safe dynamic inputs."""

    sanitized = []
    for field in list(fields or ())[:MAX_METADATA_FIELDS]:
        identifier = str(field.get("id") or "")[:64]
        if (
            not identifier
            or identifier in RESERVED_METADATA_FIELDS
            or not field_supported(field)
        ):
            continue
        allowed_values = []
        for option in list(field.get("allowedValues") or ())[:MAX_ALLOWED_VALUES]:
            if not isinstance(option, dict):
                continue
            value = option_token(option)
            label = option_label(option)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                allowed_values.append({"value": value, "label": str(label or value)[:255]})
        schema = field.get("schema") if isinstance(field.get("schema"), dict) else {}
        sanitized.append(
            {
                "id": identifier,
                "name": str(field.get("name") or identifier)[:255],
                "required": bool(field.get("required")),
                "hasDefaultValue": bool(field.get("hasDefaultValue")),
                "schema": {
                    key: str(schema[key])[:255]
                    for key in ("type", "items", "custom")
                    if schema.get(key) is not None
                },
                "allowedValues": allowed_values,
            }
        )
    return sanitized


def validate_item_field_contract(items, metadata):
    """Reject fields that were not advertised by the live JIRA create contract."""

    allowed = {field["id"]: field for field in metadata}
    unknown = sorted(
        {
            key
            for item in items
            for key in item.get("fields", {})
            if key not in allowed
        }
    )
    if unknown:
        from rest_framework.exceptions import ValidationError

        raise ValidationError(
            {"items": f"Reload JIRA fields; unsupported fields: {', '.join(unknown)}"}
        )
    required = {
        field["id"]
        for field in metadata
        if field.get("required") and not field.get("hasDefaultValue")
    }
    incomplete = [
        index
        for index, item in enumerate(items, start=1)
        if any(item.get("fields", {}).get(key) in (None, "", []) for key in required)
    ]
    if incomplete:
        from rest_framework.exceptions import ValidationError

        raise ValidationError(
            {"items": f"Required JIRA fields are missing in rows: {', '.join(map(str, incomplete[:20]))}"}
        )
    invalid = [
        index
        for index, item in enumerate(items, start=1)
        if any(
            value not in (None, "", []) and not value_supported(value, allowed[key])
            for key, value in item.get("fields", {}).items()
        )
    ]
    if invalid:
        from rest_framework.exceptions import ValidationError

        raise ValidationError(
            {"items": f"JIRA field values are invalid in rows: {', '.join(map(str, invalid[:20]))}"}
        )
