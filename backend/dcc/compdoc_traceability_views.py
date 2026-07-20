"""Permission-safe reverse CompDoc-to-DCC traceability API."""

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from awcenter.pagination import StandardResultsSetPagination
from common.compdoc_versions import latest_history_id
from jobs.models import JobStatus

from .compdoc_bridge import require_model_view_permission, resolve_compdoc_model
from .compdoc_changes import load_trace_source_changes
from .compdoc_job_sources import latest_jobs_by_trace_source
from .compdoc_refresh import refresh_availability
from .document_snapshot import DccSnapshotError
from .job_error_responses import snapshot_error_response
from .models import DccCompdocTrace
from .permissions import DCCPermission

class CompdocTraceQuerySerializer(serializers.Serializer):
    """Validate the project-scoped reverse traceability query."""

    project = serializers.RegexField(r"^[a-z0-9-]{1,64}$")
    compdoc_id = serializers.UUIDField()


@api_view(["GET"])
@permission_classes([IsAuthenticated, DCCPermission])
def compdoc_traceability_list(request):
    """Return paginated DCC usage for one authorized CompDoc record."""

    query = CompdocTraceQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    project_slug = query.validated_data["project"]
    compdoc_id = query.validated_data["compdoc_id"]
    try:
        _project, model = resolve_compdoc_model(project_slug)
        require_model_view_permission(request.user, model)
    except DccSnapshotError as error:
        return snapshot_error_response(error)
    document = get_object_or_404(model, pk=compdoc_id)
    return traceability_response(request, model, project_slug, document)


def traceability_response(request, model, project_slug, document):
    """Paginate audit rows and enrich them with retained live job state."""

    links = DccCompdocTrace.objects.filter(
        project_slug=project_slug, compdoc_id=document.pk
    ).select_related("confirmed_by")
    paginator = StandardResultsSetPagination()
    page = list(paginator.paginate_queryset(links, request))
    jobs = latest_jobs_by_trace_source(page)
    source_changes = load_trace_source_changes(model, document, page)
    current_history_id = latest_history_id(model, document.pk)
    can_create = request.user.has_perm("dcc.add_jira_dcc")
    data = [
        serialize_trace(
            link, jobs, current_history_id, source_changes[link.id],
            request.user.id, can_create,
        )
        for link in page
    ]
    return paginator.get_paginated_response(data)


def serialize_trace(
    link, jobs, current_history_id, source_change, requester_id, can_create
):
    """Return content-free provenance plus owner-safe live job metadata."""

    job = jobs.get((link.confirmed_by_id, link.job_input_sha256))
    can_open = bool(job and job.owner_id == requester_id)
    refresh_status = refresh_availability(
        link, job, current_history_id, source_change, requester_id, can_create
    )
    return {
        "id": str(link.id),
        "issue_key": link.issue_key,
        "source_history_id": link.source_history_id,
        "source_history_at": link.source_history_at,
        "source_fingerprint": link.snapshot_fingerprint,
        "confirmed_at": link.confirmed_at,
        "is_current_version": link.source_history_id == current_history_id,
        "source_change": source_change,
        "can_refresh_preview": refresh_status == "ready",
        "refresh_status": refresh_status,
        "job_status": job.status if job else "archived",
        "job_attempt": job.attempt if job else None,
        "job_completed_at": job.completed_at if job else None,
        "job_id": str(job.id) if can_open else None,
        "can_open_job": can_open,
        "output_available": bool(
            can_open and job.status == JobStatus.SUCCEEDED and job.output_file
        ),
    }
