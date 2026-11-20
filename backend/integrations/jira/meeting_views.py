"""Owned meeting imports and publication of reviewed actions under their confirmed Task."""

from collections import defaultdict

from django.db.models import Q
from django.shortcuts import get_object_or_404
from jira import JIRAError
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError

from awcenter.api_errors import error_response
from awcenter.file_security import WORD_DOCUMENT_POLICY, validate_request_upload
from jobs.api import job_creation_response
from jobs.models import Job, JobStatus
from jobs.services import calculate_upload_sha256, create_job, find_idempotent_job
from orgs.access_policy import authorized_project_ids
from orgs.models import Person, Project

from .access_policy import JIRA_DOMAIN, OPERATOR, require_resource_role
from .issue_draft_builder import load_draft_report
from .issue_draft_models import JiraIssueDraft, JiraIssueDraftStatus
from .issue_draft_serializers import JIRA_PROJECT_SLUGS
from .issue_draft_views import jira_session_error_response, reject_legacy_session_payload
from .meeting_jobs import MEETING_JOB_KIND
from .sessions import JiraSessionError, jira_connector_for
from .subtask_contracts import sanitize_subtask_fields, validate_item_field_contract
from .subtask_jobs import JOB_KIND, enqueue_subtask_batch
from .subtask_serializers import SubtaskBatchSerializer


@api_view(["POST"])
def read_minutes(request):
    error = reject_legacy_session_payload(request)
    if error:
        return error
    allowed = authorized_project_ids(request.user, JIRA_DOMAIN, OPERATOR)
    if not Project.objects.filter(pk__in=allowed, slug__in=JIRA_PROJECT_SLUGS).exists():
        raise PermissionDenied("A JIRA operator role is required.")
    file = validate_request_upload(request, "file", WORD_DOCUMENT_POLICY)
    digest = calculate_upload_sha256(file)
    previous = Job.objects.filter(
        owner=request.user, kind=MEETING_JOB_KIND, input_sha256=digest,
    ).order_by("-created_at").first()
    if previous and previous.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
        return job_creation_response(previous, False)
    # Concurrent uploads converge on one job. A failed/cancelled read can be restarted.
    operation_key = f"{digest}:{previous.id}" if previous else digest
    job, created = create_job(
        request.user, MEETING_JOB_KIND, "Read meeting minutes", {}, file,
        operation_key, getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)


@api_view(["GET", "POST"])
def meeting_actions(request, draft_id):
    error = reject_legacy_session_payload(request)
    if error:
        return error
    draft = get_object_or_404(
        JiraIssueDraft, pk=draft_id, owner=request.user, source_job__kind=MEETING_JOB_KIND,
    )
    require_resource_role(request.user, draft, OPERATOR)
    if draft.status != JiraIssueDraftStatus.PUBLISHED or not draft.jira_issue_key:
        raise ValidationError("Publish the reviewed meeting Task first.")
    operation_key = f"meeting-actions-{draft.id}"
    existing = find_idempotent_job(request.user, JOB_KIND, operation_key)
    if request.method == "GET" and existing:
        latest = Job.objects.filter(
            owner=request.user, kind=JOB_KIND,
            parameters__operation_id=existing.parameters["operation_id"],
        ).latest("created_at")
        return Response({"job_id": str(latest.id), "status": latest.status})
    try:
        connector = jira_connector_for(request.user)
        connector.set_issue(draft.jira_issue_key)
        metadata = sanitize_subtask_fields(connector.get_subtask_fields())
    except JiraSessionError as error:
        return jira_session_error_response(error)
    except JIRAError:
        return error_response("JIRA subtask fields are unavailable.", "JIRA_SUBTASK_FIELDS_UNAVAILABLE", response_status=502)
    if request.method == "GET":
        report = load_draft_report(draft.source_job)
        return Response({"actions": match_directory_assignees(report["actions"]), "fields": metadata})

    serializer = SubtaskBatchSerializer(data={
        "issue": draft.jira_issue_key, "items": request.data.get("items"),
    })
    serializer.is_valid(raise_exception=True)
    validate_item_field_contract(serializer.validated_data["items"], metadata)
    # A published meeting accepts one immutable action plan, including across reloads.
    job, created = enqueue_subtask_batch(
        request.user, draft.jira_issue_key, draft.projects.all(), serializer.validated_data["items"],
        operation_key, getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)


def match_directory_assignees(actions):
    """Suggest only unambiguous directory IDs for the names actually present in the minutes."""
    names = {item["responsible"] for item in actions if item["responsible"]}
    candidates = Person.objects.filter(Q(name__in=names) | Q(person_id__in=names))
    matches = defaultdict(set)
    for name, person_id in candidates.values_list("name", "person_id"):
        matches[name].add(person_id)
        matches[person_id].add(person_id)
    result = []
    for item in actions:
        ids = matches[item["responsible"]]
        result.append({**item, "assignee": next(iter(ids)) if len(ids) == 1 else ""})
    return result
