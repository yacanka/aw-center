"""Owner-scoped HTTP endpoints for reviewable JIRA issue drafts."""

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from jobs.models import Job

from .issue_draft_contracts import JiraDraftPreflightUnavailable, validate_session_id
from .issue_draft_models import JiraIssueDraft
from .issue_draft_preflight import inspect_create_contract
from .issue_draft_serializers import (
    JiraIssueDraftCreateSerializer, JiraIssueDraftPreflightSerializer,
    JiraIssueDraftPublishSerializer, JiraIssueDraftSerializer, JiraIssueDraftUpdateSerializer,
    JiraIssueDraftVersionSerializer,
)
from .issue_draft_services import (
    approve_issue_draft, create_issue_draft, publish_issue_draft, update_issue_draft,
)
from .service.JIRAConnector import JiraConnector


def owned_draft(user, draft_id):
    """Return one draft without revealing another owner's identifiers."""

    return get_object_or_404(
        JiraIssueDraft.objects.select_related("source_job"), pk=draft_id, owner=user
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_draft_create(request):
    """Create or replay one draft from an owned completed analysis report."""

    serializer = JiraIssueDraftCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    source_job = get_object_or_404(
        Job.objects.filter(owner=request.user), pk=serializer.validated_data["source_job_id"]
    )
    project_key = serializer.validated_data.get("project_key") or settings.JIRA_DEFAULT_PROJECT_KEY
    draft, created = create_issue_draft(request.user, source_job, project_key)
    response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response = Response(JiraIssueDraftSerializer(draft).data, status=response_status)
    if not created:
        response["Idempotency-Replayed"] = "true"
    return response


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def issue_draft_detail(request, draft_id):
    """Return or version-check a complete edit to one owned draft."""

    draft = owned_draft(request.user, draft_id)
    if request.method == "GET":
        return Response(JiraIssueDraftSerializer(draft).data)
    serializer = JiraIssueDraftUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = {key: value for key, value in serializer.validated_data.items() if key != "version"}
    draft = update_issue_draft(draft.id, request.user, values, serializer.validated_data["version"])
    return Response(JiraIssueDraftSerializer(draft).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_draft_approve(request, draft_id):
    """Record the owner's explicit approval of the current draft version."""

    draft = owned_draft(request.user, draft_id)
    serializer = JiraIssueDraftVersionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    approved = approve_issue_draft(draft.id, request.user, serializer.validated_data["version"])
    return Response(JiraIssueDraftSerializer(approved).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_draft_publish(request, draft_id):
    """Publish an approved owner draft under a dedicated Django permission."""

    draft = owned_draft(request.user, draft_id)
    require_publish_permission(request.user)
    serializer = JiraIssueDraftPublishSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    session_id = validate_session_id(serializer.validated_data["JSESSIONID"])
    published = publish_issue_draft(
        draft.id, request.user, session_id, serializer.validated_data["version"]
    )
    return Response(JiraIssueDraftSerializer(published).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_draft_preflight(request, draft_id):
    """Inspect live JIRA Task requirements without performing an external write."""

    draft = owned_draft(request.user, draft_id)
    require_publish_permission(request.user)
    serializer = JiraIssueDraftPreflightSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    session_id = validate_session_id(serializer.validated_data["JSESSIONID"])
    try:
        client = JiraConnector(settings.JIRA_URL, jira_session_id=session_id)
        result, _metadata = inspect_create_contract(draft, client)
    except Exception as error:
        raise JiraDraftPreflightUnavailable() from error
    return Response(result)


def require_publish_permission(user):
    """Require the dedicated external-side-effect permission."""

    if not user.has_perm("dcc.publish_jiraissuedraft"):
        raise PermissionDenied("You do not have permission to publish JIRA drafts.")
