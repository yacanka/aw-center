from dataclasses import asdict

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import ErrorCodes, error_response
from awcenter.file_security import MEDIA_POLICY, UploadSecurityError, validate_request_upload
from jobs.api import job_creation_response
from jobs.services import create_job
from .services import estimate_output_size, parse_parameters


def get_uploaded_file(request):
    """Return the uploaded media file or raise a validation error."""

    return validate_request_upload(request, "file", MEDIA_POLICY)


def get_request_parameters(request):
    """Return validated conversion parameters from form data."""

    return parse_parameters(request.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def preview_media(request):
    """Return an estimated output size for the requested conversion."""

    try:
        uploaded_file = get_uploaded_file(request)
        parameters = get_request_parameters(request)
        return Response(estimate_output_size(uploaded_file, parameters))
    except ValueError as error:
        return error_response(str(error), ErrorCodes.VALIDATION_ERROR, response_status=status.HTTP_400_BAD_REQUEST)
    except UploadSecurityError:
        raise


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_media_job(request):
    """Validate and enqueue a durable media conversion job."""

    try:
        uploaded_file = get_uploaded_file(request)
        parameters = get_request_parameters(request)
        job, created = create_job(
            owner=request.user,
            kind="media.convert",
            title=f"Convert {uploaded_file.name}",
            parameters=asdict(parameters),
            uploaded_file=uploaded_file,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request_id=getattr(request, "request_id", ""),
        )
        return job_creation_response(job, created)
    except ValueError as error:
        return error_response(str(error), ErrorCodes.VALIDATION_ERROR, response_status=status.HTTP_400_BAD_REQUEST)
    except UploadSecurityError:
        raise
