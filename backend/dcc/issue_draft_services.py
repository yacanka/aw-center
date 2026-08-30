"""Transactional lifecycle services for project-scoped JIRA issue drafts."""

import uuid

from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .access_policy import OPERATOR, require_projects_role, require_resource_role
from .issue_draft_builder import build_draft_content
from integrations.jira.contracts import normalize_project_key

from .issue_draft_contracts import DraftStateConflict, validate_version
from .issue_draft_models import JiraIssueDraft, JiraIssueDraftEvent, JiraIssueDraftStatus


def create_issue_draft(owner, source_job, project_key, projects, assigned_users=()):
    """Create one source-job draft after authorizing every selected project."""

    project_list = list(projects)
    assigned_list = list(assigned_users)
    require_projects_role(owner, project_list, OPERATOR)
    normalized_key = normalize_project_key(project_key)
    existing = JiraIssueDraft.objects.filter(source_job=source_job).first()
    if existing:
        require_resource_role(owner, existing, OPERATOR)
        verify_create_replay(existing, normalized_key, project_list, assigned_list)
        return existing, False
    summary, description = build_draft_content(source_job)
    fields = draft_fields(owner, source_job, normalized_key, summary, description)
    try:
        with transaction.atomic():
            draft = JiraIssueDraft.objects.create(**fields)
            draft.projects.set(project_list)
            draft.assigned_users.set(assigned_list)
            record_event(draft, owner, "created")
        return draft, True
    except IntegrityError:
        draft = JiraIssueDraft.objects.get(source_job=source_job)
        require_resource_role(owner, draft, OPERATOR)
        verify_create_replay(draft, normalized_key, project_list, assigned_list)
        return draft, False


def verify_create_replay(draft, project_key, projects, assigned_users):
    expected_projects = {project.pk for project in projects}
    expected_assignees = {user.pk for user in assigned_users}
    if (
        draft.project_key != project_key
        or set(draft.projects.values_list("pk", flat=True)) != expected_projects
        or set(draft.assigned_users.values_list("pk", flat=True)) != expected_assignees
    ):
        raise ValidationError(
            {"source_job_id": "This analysis job already has a different JIRA draft."}
        )


def draft_fields(owner, source_job, project_key, summary, description):
    draft_id = uuid.uuid4()
    return {
        "id": draft_id,
        "owner": owner,
        "source_job": source_job,
        "project_key": project_key,
        "summary": summary,
        "description": description,
        "marker_label": f"aw-center-{draft_id.hex}",
    }


def update_issue_draft(draft_id, actor, values, expected_version):
    """Apply a version-checked edit and invalidate prior approval."""

    with transaction.atomic():
        draft = lock_draft(draft_id)
        require_resource_role(actor, draft, OPERATOR)
        validate_version(draft.version, expected_version)
        ensure_editable(draft)
        projects = list(values.pop("projects", draft.projects.all()))
        require_projects_role(actor, projects, OPERATOR)
        assigned_users = values.pop("assigned_users", None)
        apply_edit(draft, values)
        draft.projects.set(projects)
        if assigned_users is not None:
            draft.assigned_users.set(assigned_users)
        record_event(draft, actor, "updated")
    return draft


def apply_edit(draft, values):
    if "project_key" in values:
        draft.project_key = normalize_project_key(values["project_key"])
    if "summary" in values:
        draft.summary = values["summary"].strip()
    if "description" in values:
        draft.description = values["description"].strip()
    if "extra_fields" in values:
        draft.extra_fields = values["extra_fields"]
    draft.status = JiraIssueDraftStatus.DRAFT
    draft.approved_by = None
    draft.approved_at = None
    clear_failure(draft)
    draft.version += 1
    draft.save()


def approve_issue_draft(draft_id, actor, expected_version):
    """Record an operator's explicit approval of the current draft version."""

    with transaction.atomic():
        draft = lock_draft(draft_id)
        require_resource_role(actor, draft, OPERATOR)
        validate_version(draft.version, expected_version)
        if draft.status != JiraIssueDraftStatus.DRAFT:
            raise DraftStateConflict()
        draft.status = JiraIssueDraftStatus.APPROVED
        draft.approved_by = actor
        draft.approved_at = timezone.now()
        draft.version += 1
        draft.save()
        record_event(draft, actor, "approved")
    return draft


def lock_draft(draft_id):
    try:
        return (
            JiraIssueDraft.objects.select_for_update()
            .prefetch_related("projects", "assigned_users")
            .get(pk=draft_id)
        )
    except JiraIssueDraft.DoesNotExist as error:
        raise Http404 from error


def ensure_editable(draft):
    if draft.status in {
        JiraIssueDraftStatus.PUBLISHING,
        JiraIssueDraftStatus.PUBLISHED,
        JiraIssueDraftStatus.RECONCILIATION_REQUIRED,
    }:
        raise DraftStateConflict()


def clear_failure(draft):
    draft.last_error_code = ""
    draft.last_error_message = ""


def record_event(draft, actor, event_type, details=None):
    return JiraIssueDraftEvent.objects.create(
        draft=draft,
        actor=actor,
        event_type=event_type,
        version=draft.version,
        details=details or {},
    )
