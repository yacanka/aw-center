"""Field-building helpers shared by JIRA publication executors."""

from .contracts import validate_issue_key
from .create_contract import ensure_contract_ready, inspect_create_contract
from .field_values import build_extra_issue_fields


def find_existing_issue(draft, client):
    issue = client.find_issue_by_label(draft.marker_label)
    return validate_issue_key(issue.key) if issue else None


def build_create_fields(draft, client, *, category_label="aw-center-document-analysis"):
    preflight, metadata = inspect_create_contract(draft, client)
    ensure_contract_ready(preflight)
    fields = {
        "project": draft.project_key,
        "summary": draft.summary,
        "description": draft.description,
        "issuetype": {"name": "Task"},
        "labels": [draft.marker_label, category_label],
    }
    fields.update(build_extra_issue_fields(draft, metadata))
    return fields
