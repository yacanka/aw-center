from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils import timezone

from awcenter.api_errors import error_response
from awcenter.private_files import PrivateFileIntegrityError, open_verified_private_file
from .models import Job, WorkerHeartbeat
from .serializers import JobDetailSerializer, JobSerializer
from .services import request_cancellation


def owned_jobs(request):
    """Return jobs visible to the authenticated caller."""

    return Job.objects.filter(owner=request.user).select_related("owner", "jira_issue_draft")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_list(request):
    """List caller-owned jobs using the configured pagination contract."""

    queryset = owned_jobs(request)
    from awcenter.pagination import StandardResultsSetPagination
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(JobSerializer(page, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_detail(request, job_id):
    """Return one owned job and its audit history."""

    job = get_object_or_404(owned_jobs(request), pk=job_id)
    return Response(JobDetailSerializer(job).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_job(request, job_id):
    """Cancel or cooperatively request cancellation of an owned job."""

    job = get_object_or_404(owned_jobs(request), pk=job_id)
    updated = request_cancellation(job)
    return Response(JobSerializer(updated).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_job_output(request, job_id):
    """Stream the completed output artifact to its owner."""

    job = get_object_or_404(owned_jobs(request), pk=job_id, status="succeeded")
    if not job.output_file:
        return error_response(
            "Job output is unavailable.",
            "JOB_OUTPUT_MISSING",
            response_status=404,
        )
    try:
        output = open_verified_private_file(job.output_file, job.output_sha256)
    except (OSError, PrivateFileIntegrityError):
        return error_response(
            "Job output failed integrity verification.",
            "JOB_OUTPUT_INTEGRITY_FAILED",
            response_status=409,
        )
    return FileResponse(output, as_attachment=True, filename=job.output_name)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_system_status(request):
    """Return worker availability and owner-scoped queue counts."""

    stale_seconds = max(5, int(settings.JOB_WORKER_STALE_SECONDS))
    active_since = timezone.now() - timedelta(seconds=stale_seconds)
    active_workers = WorkerHeartbeat.objects.filter(
        heartbeat_at__gte=active_since
    ).exclude(worker_id__startswith="windows:").count()
    counts = owned_jobs(request).values("status").annotate(total=Count("id"))
    return Response({
        "available": active_workers > 0,
        "active_workers": active_workers,
        "counts": {item["status"]: item["total"] for item in counts},
    })
