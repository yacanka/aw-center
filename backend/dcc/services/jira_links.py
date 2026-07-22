"""Build browser-safe JIRA issue links from backend configuration."""

from urllib.parse import quote, urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def build_jira_issue_url(issue_key: object) -> str:
    """Return the configured JIRA browse URL for one non-empty issue key."""

    base_url = str(settings.JIRA_URL).strip().rstrip("/")
    parsed_url = urlsplit(base_url)
    has_unsafe_parts = parsed_url.username or parsed_url.password or parsed_url.query
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ImproperlyConfigured("JIRA_URL must be an absolute HTTP(S) URL.")
    if has_unsafe_parts or parsed_url.fragment:
        raise ImproperlyConfigured("JIRA_URL cannot contain credentials, query, or fragment.")
    normalized_key = str(issue_key).strip()
    if not normalized_key:
        raise ValueError("JIRA issue key cannot be empty.")
    encoded_key = quote(normalized_key, safe="-._~")
    return f"{base_url}/browse/{encoded_key}"


def attach_jira_issue_urls(payload: dict) -> dict:
    """Attach backend-owned links to a JIRA issue payload and its subtasks."""

    if payload.get("key"):
        payload["jira_issue_url"] = build_jira_issue_url(payload["key"])
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return payload
    subtasks = fields.get("subtasks")
    if not isinstance(subtasks, list):
        return payload
    for subtask in subtasks:
        if isinstance(subtask, dict) and subtask.get("key"):
            subtask["jira_issue_url"] = build_jira_issue_url(subtask["key"])
    return payload
