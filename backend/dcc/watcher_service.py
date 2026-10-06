"""Project-authorized Watcher import and bounded live JIRA status projection."""

import re
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from integrations.jira.sessions import jira_connector_for
from integrations.jira.client import is_completed_status
from .access_policy import OPERATOR, VIEWER, require_projects_role, require_resource_role
from .document_fields import field
from .document_snapshot import DccSnapshotError, resolve_enabled_projects, validate_parent_issue
from .models import DccRecord
from .record_services import create_record
from .services.jira_links import build_jira_issue_url
from .services.project_resolver import DccProjectResolutionError, resolve_projects_from_jira_components


class WatcherDuplicate(APIException):
    status_code = 409
    default_code = "DCC_RECORD_ALREADY_TRACKED"
    default_detail = "You already track this JIRA issue."


def watcher_issue_key(reference):
    """Accept only a key or a browse link on the configured JIRA origin/path."""
    value = reference.strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,19}-[1-9][0-9]*", value, re.I):
        try:
            base, url = urlsplit(settings.JIRA_URL.rstrip("/")), urlsplit(value)
        except ValueError as error:
            raise DccSnapshotError("Enter a valid JIRA browse URL.", "DCC_ISSUE_INVALID") from error
        prefix = base.path.rstrip("/") + "/browse/"
        if (url.scheme != base.scheme or url.netloc != base.netloc or
                url.username or url.password or not url.path.startswith(prefix)):
            raise DccSnapshotError("Enter a configured JIRA browse URL or issue key.", "DCC_ISSUE_INVALID")
        value = url.path[len(prefix):]
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,19}-[1-9][0-9]*", value, re.I):
        raise DccSnapshotError("Enter a valid JIRA issue key.", "DCC_ISSUE_INVALID")
    return value.upper()


def read_issue(actor, key):
    connector = jira_connector_for(actor)
    connector.set_issue(key)
    issue = connector.get_issue()
    validate_parent_issue(issue)
    try:
        definitions = resolve_projects_from_jira_components(field(issue.fields, "components") or [])
    except DccProjectResolutionError as error:
        raise DccSnapshotError("The JIRA task does not identify a supported DCC project.",
                               "DCC_PROJECT_INVALID") from error
    return issue, resolve_enabled_projects(definitions)


def import_watcher_record(actor, reference):
    """Resolve trusted metadata; serialize same-owner imports without holding locks over I/O."""
    key = watcher_issue_key(reference)
    issue, projects = read_issue(actor, key)
    require_projects_role(actor, projects, OPERATOR)
    # JIRA may redirect an old key after moving an issue to another project.
    key = watcher_issue_key(str(field(issue, "key") or ""))
    title = str(field(issue.fields, "summary") or "").strip()
    if not title or len(title) > 255:
        raise DccSnapshotError("The JIRA task has an invalid title.", "DCC_ISSUE_INVALID")
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=actor.pk)
        if DccRecord.objects.filter(owner=actor, issue=key).exists():
            raise WatcherDuplicate()
        return create_record(actor, {"issue": key, "title": title, "projects": projects})


def live_watcher_status(actor, record):
    require_resource_role(actor, record, VIEWER)
    issue, projects = read_issue(actor, record.issue)
    require_projects_role(actor, projects, VIEWER)
    if {project.pk for project in projects} != set(record.projects.values_list("pk", flat=True)):
        raise DccSnapshotError("The record projects no longer match the JIRA task.",
                               "DCC_PROJECT_MISMATCH", 409)
    subtasks = [status_item(task) for task in field(issue.fields, "subtasks") or []]
    status = status_item(issue)
    return {
        **status,
        "subtasks": subtasks,
        "completed": all(task["completed"] for task in subtasks) if subtasks else status["completed"],
        "ecd_number": text_field(issue.fields, "customfield_45000"),
        "ecd_revision": text_field(issue.fields, "customfield_45001"),
        "dcc_number": text_field(issue.fields, "customfield_45002"),
        "checked_at": timezone.now().isoformat(),
    }


def status_item(issue):
    key = watcher_issue_key(str(field(issue, "key") or ""))
    fields = field(issue, "fields")
    status = field(fields, "status")
    name = text_field(status, "name")
    completed = is_completed_status(status)
    return {"issue": key, "title": text_field(fields, "summary"), "status": name,
            "completed": completed, "jira_issue_url": build_jira_issue_url(key)}


def text_field(value, name):
    return str(field(value, name) or "")[:255]
