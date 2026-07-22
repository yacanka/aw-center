import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import ErrorCodes, error_response

from .client import DoorsConnectionError, DoorsDxlError, DoorsOperationError
from .serializers import (
    ModuleSerializer,
    ObjectCreateSerializer,
    ObjectDetailSerializer,
    ObjectListSerializer,
    ObjectUpdateSerializer,
)
from .services import execute_with_client, integration_status

LOGGER = logging.getLogger(__name__)


def validate(serializer_class, data):
    """Validate request data and return values or a contract response."""
    serializer = serializer_class(data=data)
    if serializer.is_valid():
        return serializer.validated_data, None
    response = error_response(
        "Invalid DOORS request.",
        ErrorCodes.VALIDATION_ERROR,
        errors=serializer.errors,
        response_status=status.HTTP_400_BAD_REQUEST,
    )
    return None, response


def execute(operation):
    """Execute a DOORS operation with user-actionable error mapping."""
    try:
        return Response(execute_with_client(operation))
    except DoorsConnectionError as error:
        return doors_error(str(error), "DOORS_UNAVAILABLE", 503)
    except DoorsOperationError as error:
        LOGGER.warning("DOORS operation failed with code %s", error.code)
        return doors_error(str(error), "DOORS_OPERATION_FAILED", 502)
    except DoorsDxlError as error:
        LOGGER.warning("DOORS DXL transport failed: %s", type(error).__name__)
        return doors_error(str(error), "DOORS_OPERATION_FAILED", 502)
    except ValueError:
        return doors_error("Invalid DOORS operation parameters.", ErrorCodes.VALIDATION_ERROR, 400)


def doors_error(detail: str, code: str, response_status: int):
    """Return a standardized DOORS integration error."""
    return error_response(detail, code, response_status=response_status)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_view(request):
    """Return non-secret DOORS configuration status."""
    return Response(integration_status())


@api_view(["POST"])
@permission_classes([IsAdminUser])
def application_result_probe(request):
    """Verify a fixed DXL payload through oleSetResult/Application.Result."""
    return execute(lambda client: application_result_probe_response(client))


def application_result_probe_response(client):
    """Return the non-secret Application.Result round-trip payload."""
    result = client.probe_application_result()
    return {"available": True, "result_mode": "application_result", "lines": result.raw_lines}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def check_module(request):
    """Check whether an authenticated DOORS client can read a module."""
    values, failure = validate(ModuleSerializer, request.data)
    if failure:
        return failure
    return execute(
        lambda client: {
            "accessible": client.check_module(values["module_path"]).ok,
            "module_path": values["module_path"],
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def list_objects(request):
    """Return a bounded list of objects from a DOORS module."""
    values, failure = validate(ObjectListSerializer, request.data)
    if failure:
        return failure
    return execute(lambda client: list_object_response(client, values))


def list_object_response(client, values):
    """Build a stable DOORS object-list API response."""
    objects = client.list_objects(
        values["module_path"], values["attributes"], values["loop"], values["limit"]
    )
    return {"count": len(objects), "results": [item.to_dict() for item in objects]}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_object(request):
    """Return one DOORS object by absolute number."""
    values, failure = validate(ObjectDetailSerializer, request.data)
    if failure:
        return failure
    return execute(
        lambda client: client.get_object(
            values["module_path"], values["absolute_number"], values["attributes"]
        ).to_dict()
    )


@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def update_object(request):
    """Update scalar DOORS attributes for an administrator user."""
    values, failure = validate(ObjectUpdateSerializer, request.data)
    if failure:
        return failure
    return execute(lambda client: update_object_response(client, values))


def update_object_response(client, values):
    """Execute an object update and return a stable success response."""
    client.set_object_attributes(
        values["module_path"], values["absolute_number"], values["attributes"]
    )
    return {"updated": True, "absolute_number": values["absolute_number"]}


@api_view(["POST"])
@permission_classes([IsAdminUser])
def create_object(request):
    """Create a DOORS object for an administrator user."""
    values, failure = validate(ObjectCreateSerializer, request.data)
    if failure:
        return failure
    return execute(lambda client: create_object_response(client, values))


def create_object_response(client, values):
    """Execute object creation and return its stable representation."""
    created = client.create_object(
        values["module_path"],
        values["position"],
        values.get("relative_absolute_number"),
        values["attributes"],
    )
    return created.to_dict()
