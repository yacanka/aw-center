from pathlib import Path

from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import ErrorCodes, error_response
from .services import convert_uploaded_media, estimate_output_size, parse_parameters


def get_uploaded_file(request):
    """Return the uploaded media file or raise a validation error."""

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        raise ValueError("Media file is required.")
    return uploaded_file


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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def convert_media(request):
    """Convert an uploaded image, audio, or video file with FFmpeg."""

    try:
        uploaded_file = get_uploaded_file(request)
        parameters = get_request_parameters(request)
        output_path = convert_uploaded_media(uploaded_file, parameters)
        return create_download_response(output_path)
    except ValueError as error:
        return error_response(str(error), ErrorCodes.VALIDATION_ERROR, response_status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        return error_response("Media conversion failed.", ErrorCodes.ERROR, response_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def create_download_response(output_path: Path) -> FileResponse:
    """Create a download response for a generated conversion file."""

    response = FileResponse(output_path.open("rb"), as_attachment=True, filename=output_path.name)
    response["Content-Type"] = "application/octet-stream"
    original_close = response.close

    def close_with_cleanup():
        original_close()
        output_path.unlink(missing_ok=True)

    response.close = close_with_cleanup
    return response
