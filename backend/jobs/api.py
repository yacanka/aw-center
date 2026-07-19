from rest_framework import status
from rest_framework.response import Response

from .serializers import JobSerializer


def job_creation_response(job, created):
    """Return a consistent create-or-idempotent-replay API response."""

    response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response = Response(JobSerializer(job).data, status=response_status)
    if not created:
        response["Idempotency-Replayed"] = "true"
    return response
