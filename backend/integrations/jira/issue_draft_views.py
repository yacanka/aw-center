"""Canonical project-scoped HTTP endpoints for JIRA issue drafts."""

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import error_response
from integrations.jira.contracts import JiraDraftPreflightUnavailable
from integrations.jira.create_contract import inspect_create_contract
from integrations.jira.sessions import (
    JiraSessionError,
    has_legacy_jira_credential,
    jira_connector_for,
)
from jobs.api import job_creation_response
from jobs.models import Job

from .access_policy import OPERATOR, PUBLISHER, VIEWER, require_resource_role
from .issue_draft_contracts import validate_version
from .issue_draft_models import JiraIssueDraft
from .issue_draft_serializers import (
    JiraIssueDraftCreateSerializer,
    JiraIssueDraftPreflightSerializer,
    JiraIssueDraftPublishSerializer,
    JiraIssueDraftSerializer,
    JiraIssueDraftUpdateSerializer,
    JiraIssueDraftVersionSerializer,
)
from .issue_draft_services import (
    approve_issue_draft,
    create_issue_draft,
    update_issue_draft,
)
from .publication_jobs import enqueue_draft_publication


def subject_draft(user, draft_id):
    queryset = JiraIssueDraft.objects.select_related("source_job").prefetch_related(
        "projects", "assigned_users"
    )
    if not user.is_superuser:
        queryset = queryset.filter(Q(owner=user) | Q(assigned_users=user)).distinct()
    return get_object_or_404(queryset, pk=draft_id)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_draft_create(request):
    legacy_error = reject_legacy_session_payload(request)
    if legacy_error:
        return legacy_error
    serializer = JiraIssueDraftCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    source_job = get_object_or_404(
        Job.objects.filter(owner=request.user),
        pk=serializer.validated_data["source_job_id"],
    )
    project_key = (
        serializer.validated_data.get("project_key")
        or settings.JIRA_DEFAULT_PROJECT_KEY
    )
    draft, created = create_issue_draft(
        request.user,
        source_job,
        project_key,
        serializer.validated_data["projects"],
        serializer.validated_data.get("assigned_users", ()),
    )
    response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response = Response(serialize_draft(draft, request), status=response_status)
    if not created:
        response["Idempotency-Replayed"] = "true"
    return response


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def issue_draft_detail(request, draft_id):
    legacy_error = reject_legacy_session_payload(request)
    if legacy_error:
        return legacy_error
    draft = subject_draft(request.user, draft_id)
    if request.method == "GET":
        require_resource_role(request.user, draft, VIEWER)
        return Response(serialize_draft(draft, request))
    require_resource_role(request.user, draft, OPERATOR)
    serializer = JiraIssueDraftUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    expected_version = values.pop("version")
    updated = update_issue_draft(draft.id, request.user, values, expected_version)
    return Response(serialize_draft(updated, request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_draft_approve(request, draft_id):
    legacy_error = reject_legacy_session_payload(request)
    if legacy_error:
        return legacy_error
    draft = subject_draft(request.user, draft_id)
    require_resource_role(request.user, draft, OPERATOR)
    serializer = JiraIssueDraftVersionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    approved = approve_issue_draft(
        draft.id,
        request.user,
        serializer.validated_data["version"],
    )
    return Response(serialize_draft(approved, request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_draft_publish(request, draft_id):
    legacy_error = reject_legacy_session_payload(request)
    if legacy_error:
        return legacy_error
    draft = subject_draft(request.user, draft_id)
    require_resource_role(request.user, draft, PUBLISHER)
    serializer = JiraIssueDraftPublishSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    job, created = enqueue_draft_publication(
        request.user,
        draft.id,
        serializer.validated_data["version"],
        request.headers.get("Idempotency-Key", ""),
        reconcile=serializer.validated_data["reconcile"],
        request_id=getattr(request, "request_id", ""),
    )
    return job_creation_response(job, created)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_draft_preflight(request, draft_id):
    legacy_error = reject_legacy_session_payload(request)
    if legacy_error:
        return legacy_error
    draft = subject_draft(request.user, draft_id)
    require_resource_role(request.user, draft, PUBLISHER)
    serializer = JiraIssueDraftPreflightSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    validate_version(draft.version, serializer.validated_data["version"])
    try:
        client = jira_connector_for(request.user)
        result, _metadata = inspect_create_contract(draft, client)
    except JiraSessionError as error:
        return jira_session_error_response(error)
    except Exception as error:
        raise JiraDraftPreflightUnavailable() from error
    return Response(result)


def reject_legacy_session_payload(request):
    if not has_legacy_jira_credential((request.data, request.query_params)):
        return None
    return error_response(
        "Connect JIRA through the integrations session endpoint.",
        code="JIRA_SESSION_CANONICAL_REQUIRED",
        response_status=400,
    )


def jira_session_error_response(error):
    return error_response(
        error.detail,
        code=error.code,
        response_status=error.response_status,
    )


def serialize_draft(draft, request):
    return JiraIssueDraftSerializer(draft, context={"request": request}).data
