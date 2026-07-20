"""Authenticated APIs for reusable multi-step workflow runs."""

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.file_security import validate_request_upload
from awcenter.pagination import StandardResultsSetPagination

from .models import Job
from .workflow_controls import cancel_workflow
from .workflow_models import WorkflowRun
from .workflow_recipes import get_workflow_recipe, workflow_recipe_catalog
from .workflow_serializers import WorkflowRunDetailSerializer, WorkflowRunSerializer
from .workflow_services import create_workflow_run


def owned_workflows(request):
    """Return workflow runs owned by the authenticated caller."""

    jobs = Job.objects.order_by("workflow_step", "attempt", "created_at")
    return WorkflowRun.objects.filter(owner=request.user).prefetch_related(
        Prefetch("jobs", queryset=jobs)
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workflow_recipe_list(request):
    """List safe workflow recipes available to the caller."""

    return Response(workflow_recipe_catalog())


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def workflow_list_create(request):
    """List owned workflow runs or enqueue a validated recipe."""

    if request.method == "POST":
        return create_workflow_response(request)
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(owned_workflows(request), request)
    return paginator.get_paginated_response(WorkflowRunSerializer(page, many=True).data)


def create_workflow_response(request):
    """Validate one workflow upload and return idempotent creation metadata."""

    recipe = get_workflow_recipe(request.data.get("recipe"))
    upload = validate_request_upload(request, "file", recipe.upload_policy)
    workflow, created = create_workflow_run(
        request.user, recipe.identifier, request.data, upload,
        request.headers.get("Idempotency-Key", ""), getattr(request, "request_id", ""),
    )
    code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response = Response(WorkflowRunSerializer(workflow).data, status=code)
    if not created:
        response["Idempotency-Replayed"] = "true"
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workflow_detail(request, workflow_id):
    """Return one owned workflow with its bounded audit trail."""

    workflow = get_object_or_404(owned_workflows(request), pk=workflow_id)
    return Response(WorkflowRunDetailSerializer(workflow).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_workflow_run(request, workflow_id):
    """Cancel the active jobs of one owned workflow run."""

    workflow = get_object_or_404(owned_workflows(request), pk=workflow_id)
    return Response(WorkflowRunSerializer(cancel_workflow(workflow)).data)
