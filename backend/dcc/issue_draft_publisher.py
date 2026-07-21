"""External JIRA publication adapter with duplicate-recovery semantics."""

from django.conf import settings

from .issue_draft_contracts import validate_issue_key
from .issue_draft_field_values import build_extra_issue_fields
from .issue_draft_preflight import ensure_contract_ready, inspect_create_contract
from .service.JIRAConnector import JiraConnector


def publish_to_jira(draft, session_id):
    """Find or create the marker-labelled JIRA task and return its key."""

    client = JiraConnector(server_url=settings.JIRA_URL, jira_session_id=session_id)
    existing = client.find_issue_by_label(draft.marker_label)
    if existing:
        return validate_issue_key(existing.key)
    preflight, metadata = inspect_create_contract(draft, client)
    ensure_contract_ready(preflight)
    issue = client.create_issue(build_issue_fields(draft, metadata))
    return validate_issue_key(issue.key)


def build_issue_fields(draft, metadata):
    """Build validated Task fields plus live create-screen extension values."""

    fields = {
        "project": draft.project_key,
        "summary": draft.summary,
        "description": draft.description,
        "issuetype": {"name": "Task"},
        "labels": [draft.marker_label, "aw-center-document-analysis"],
    }
    fields.update(build_extra_issue_fields(draft, metadata))
    return fields
