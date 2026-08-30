"""Canonical owner-scoped HTTP surface for ECR workflows."""

from types import SimpleNamespace

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import error_response
from awcenter.file_security import UploadPolicy, validate_request_upload
from awcenter.pagination import StandardResultsSetPagination
from integrations.jira.create_contract import inspect_create_contract, safe_identity
from integrations.jira.contracts import JiraDraftPreflightUnavailable
from integrations.jira.sessions import (
    JiraSessionError,
    has_legacy_jira_credential,
    jira_connector_for,
)

from .ecr_access import OPERATOR, readable_ecr_workflows, require_ecr_role
from .ecr_contracts import EcrStateConflict, ecr_parent_description, validate_ecr_version
from .ecr_publication_jobs import enqueue_ecr_publication
from .ecr_serializers import (
    EcrApprovalSerializer,
    EcrCreateSerializer,
    EcrVersionSerializer,
    EcrWorkflowDetailSerializer,
    EcrWorkflowSerializer,
    parse_project_slugs,
)
from .ecr_services import (
    approve_ecr_workflow,
    create_ecr_workflow,
    reject_ecr_workflow,
)
from .models import EcrWorkflow, EcrWorkflowStatus

ECR_PDF_POLICY = UploadPolicy(
    frozenset({".pdf"}),
    "ECR_MAX_PDF_BYTES",
    10 * 1024 * 1024,
)


def owned_ecr_workflows(request):
    queryset = (
        EcrWorkflow.objects.all()
        .select_related("publication_job")
        .prefetch_related("projects")
    )
    return readable_ecr_workflows(request.user, queryset).order_by(
        "-updated_at",
        "-id",
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def ecr_workflow_collection(request):
    """List owned ECR workflows or create one immutable PDF review."""

    legacy_error = reject_credential_payload(request)
    if legacy_error:
        return legacy_error
    if request.method == "POST":
        return create_ecr_response(request)
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(owned_ecr_workflows(request), request)
    serializer = EcrWorkflowSerializer(
        page,
        many=True,
        context={"request": request},
    )
    return paginator.get_paginated_response(serializer.data)


def create_ecr_response(request):
    upload = validate_request_upload(request, "file", ECR_PDF_POLICY)
    serializer = EcrCreateSerializer(
        data={"project_slugs": parse_project_slugs(request.data)}
    )
    serializer.is_valid(raise_exception=True)
    workflow, created = create_ecr_workflow(
        request.user,
        serializer.validated_data["project_slugs"],
        upload,
        request.headers.get("Idempotency-Key", ""),
    )
    response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response = Response(
        serialize_workflow(workflow, request),
        status=response_status,
    )
    if not created:
        response["Idempotency-Replayed"] = "true"
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ecr_workflow_detail(request, workflow_id):
    legacy_error = reject_credential_payload(request)
    if legacy_error:
        return legacy_error
    workflow = get_object_or_404(owned_ecr_workflows(request), pk=workflow_id)
    return Response(
        EcrWorkflowDetailSerializer(
            workflow,
            context={"request": request},
        ).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ecr_workflow_approve(request, workflow_id):
    legacy_error = reject_credential_payload(request)
    if legacy_error:
        return legacy_error
    get_object_or_404(owned_ecr_workflows(request), pk=workflow_id)
    serializer = EcrApprovalSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    workflow = approve_ecr_workflow(
        workflow_id,
        request.user,
        serializer.validated_data,
    )
    return Response(serialize_workflow(workflow, request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ecr_workflow_preflight(request, workflow_id):
    """Inspect JIRA requirements for the exact unapproved ECR plan."""

    legacy_error = reject_credential_payload(request)
    if legacy_error:
        return legacy_error
    workflow = get_object_or_404(owned_ecr_workflows(request), pk=workflow_id)
    require_ecr_role(request.user, workflow, OPERATOR)
    serializer = EcrApprovalSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    validate_ecr_version(workflow.version, values["version"])
    if workflow.status != EcrWorkflowStatus.REVIEW:
        raise EcrStateConflict()
    draft = SimpleNamespace(
        project_key=values["project_key"],
        summary=str(workflow.snapshot.get("title") or "")[:255],
        description=ecr_parent_description(workflow.snapshot),
        extra_fields=values.get("extra_fields", {}),
    )
    try:
        connector = jira_connector_for(request.user)
        result, _metadata = inspect_create_contract(
            draft,
            connector,
        )
        if values.get("subtasks"):
            result = _include_subtask_contract(result, connector, values["project_key"])
    except JiraSessionError as error:
        return error_response(error.detail, error.code, response_status=error.response_status)
    except Exception as error:
        raise JiraDraftPreflightUnavailable() from error
    return Response(result)


def _include_subtask_contract(result, connector, project_key):
    supported_fields = {
        "project",
        "summary",
        "description",
        "issuetype",
        "parent",
        "labels",
        "assignee",
        "priority",
        "duedate",
    }
    metadata = connector.get_create_fields(project_key, "Sub-task")
    blockers = [
        safe_identity(field.get("id"), field.get("name"))
        for field in metadata
        if field.get("required")
        and not field.get("hasDefaultValue")
        and field.get("id") not in supported_fields
    ]
    if blockers:
        known = {item["id"] for item in result["unsupported_fields"]}
        result["unsupported_fields"].extend(
            item for item in blockers if item["id"] not in known
        )
    result["issue_type"] = "Task + Sub-task"
    result["ready"] = not any(
        result[key]
        for key in ("missing_fields", "invalid_fields", "unsupported_fields")
    )
    return result


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ecr_workflow_reject(request, workflow_id):
    legacy_error = reject_credential_payload(request)
    if legacy_error:
        return legacy_error
    get_object_or_404(owned_ecr_workflows(request), pk=workflow_id)
    serializer = EcrVersionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    workflow = reject_ecr_workflow(
        workflow_id,
        request.user,
        serializer.validated_data["version"],
    )
    return Response(serialize_workflow(workflow, request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ecr_workflow_publish(request, workflow_id):
    return publication_response(request, workflow_id, action="publish")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ecr_workflow_resume(request, workflow_id):
    return publication_response(request, workflow_id, action="resume")


def publication_response(request, workflow_id, *, action):
    legacy_error = reject_credential_payload(request)
    if legacy_error:
        return legacy_error
    workflow = get_object_or_404(owned_ecr_workflows(request), pk=workflow_id)
    serializer = EcrVersionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        workflow, _job, created = enqueue_ecr_publication(
            request.user,
            workflow_id,
            serializer.validated_data["version"],
            request.headers.get("Idempotency-Key", ""),
            action=action,
            request_id=getattr(request, "request_id", ""),
        )
    except JiraSessionError as error:
        return error_response(
            error.detail,
            error.code,
            response_status=error.response_status,
        )
    response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response = Response(
        serialize_workflow(workflow, request),
        status=response_status,
    )
    if not created:
        response["Idempotency-Replayed"] = "true"
    return response


def serialize_workflow(workflow, request):
    return EcrWorkflowSerializer(workflow, context={"request": request}).data


def reject_credential_payload(request):
    values = [request.query_params]
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        values.append(request.data)
    if not any(has_legacy_jira_credential(value) for value in values):
        return None
    return error_response(
        "Connect JIRA through the integrations session endpoint.",
        code="JIRA_SESSION_CANONICAL_REQUIRED",
        response_status=400,
    )
