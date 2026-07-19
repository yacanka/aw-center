from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils import timezone

from .models import Job, JobStatus, WorkerHeartbeat
from .serializers import JobDetailSerializer, JobSerializer
from .services import request_cancellation, retry_job


def owned_jobs(request):
    """Return jobs visible to the authenticated caller."""

    queryset = Job.objects.filter(owner=request.user)
    if request.user.is_staff and request.query_params.get("scope") == "all":
        queryset = Job.objects.all()
    return queryset.select_related("owner", "retry_of")


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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def retry_failed_job(request, job_id):
    """Queue a new attempt for an owned failed or cancelled job."""

    job = get_object_or_404(owned_jobs(request), pk=job_id)
    retried = retry_job(job)
    return Response(JobSerializer(retried).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_job_output(request, job_id):
    """Stream the completed output artifact to its owner."""

    job = get_object_or_404(owned_jobs(request), pk=job_id, status="succeeded")
    if not job.output_file:
        return Response({"detail": "Job output is unavailable.", "code": "JOB_OUTPUT_MISSING"}, status=404)
    return FileResponse(job.output_file.open("rb"), as_attachment=True, filename=job.output_name)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_system_status(request):
    """Return worker availability and owner-scoped queue counts."""

    stale_seconds = max(5, int(settings.JOB_WORKER_STALE_SECONDS))
    active_since = timezone.now() - timedelta(seconds=stale_seconds)
    active_workers = WorkerHeartbeat.objects.filter(heartbeat_at__gte=active_since).count()
    counts = owned_jobs(request).values("status").annotate(total=Count("id"))
    return Response({
        "available": active_workers > 0,
        "active_workers": active_workers,
        "counts": {item["status"]: item["total"] for item in counts},
    })
