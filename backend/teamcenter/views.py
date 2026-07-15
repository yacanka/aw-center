import logging
from collections import defaultdict

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import ErrorCodes, error_response

from .exceptions import (
    TeamcenterAuthenticationError,
    TeamcenterConfigurationError,
    TeamcenterConnectionError,
    TeamcenterProtocolError,
    TeamcenterServiceError,
)
from .models import ModelReference, PropertyUpdate
from .serializers import (
    ExecuteSavedQuerySerializer,
    GetPropertiesSerializer,
    LoadObjectsSerializer,
    SetPropertiesSerializer,
)
from .services import execute_with_client, integration_status

LOGGER = logging.getLogger(__name__)


def validate(serializer_class, data):
    """Validate request data and return values or a contract response."""
    serializer = serializer_class(data=data)
    if serializer.is_valid():
        return serializer.validated_data, None
    response = error_response(
        "Invalid Teamcenter request.",
        ErrorCodes.VALIDATION_ERROR,
        errors=serializer.errors,
        response_status=status.HTTP_400_BAD_REQUEST,
    )
    return None, response


def execute(operation):
    """Execute a Teamcenter operation with sanitized error mapping."""
    try:
        return Response(execute_with_client(operation))
    except TeamcenterConfigurationError:
        return integration_error("Teamcenter is not configured.", "TEAMCENTER_NOT_CONFIGURED", 503)
    except TeamcenterAuthenticationError:
        return integration_error("Teamcenter authentication failed.", "TEAMCENTER_AUTH_FAILED", 502)
    except (TeamcenterConnectionError, TeamcenterProtocolError, TeamcenterServiceError) as error:
        LOGGER.warning("Teamcenter operation failed: %s", type(error).__name__)
        return integration_error("Teamcenter operation failed.", "TEAMCENTER_OPERATION_FAILED", 502)
    except ValueError:
        return integration_error("Invalid Teamcenter operation parameters.", ErrorCodes.VALIDATION_ERROR, 400)


def integration_error(detail: str, code: str, response_status: int):
    """Return a standardized integration error response."""
    return error_response(detail, code, response_status=response_status)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_view(request):
    """Return non-secret Teamcenter configuration status."""
    return Response(integration_status())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def probe(request):
    """Authenticate and report whether Teamcenter is reachable."""
    return execute(lambda client: {"connected": True, "service_root": client.config.service_root})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def saved_queries(request):
    """Return saved queries visible to the configured account."""
    return execute(lambda client: client.find_saved_queries())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def execute_saved_query(request):
    """Execute a bounded Teamcenter saved query."""
    values, failure = validate(ExecuteSavedQuerySerializer, request.data)
    if failure:
        return failure
    return execute(
        lambda client: client.execute_saved_query(
            values["query_uid"], values["entries"], values["values"], values["maximum"]
        )
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def load_objects(request):
    """Load a bounded list of Teamcenter objects."""
    values, failure = validate(LoadObjectsSerializer, request.data)
    if failure:
        return failure
    return execute(lambda client: client.load_objects(values["uids"]))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_properties(request):
    """Read selected Teamcenter properties."""
    values, failure = validate(GetPropertiesSerializer, request.data)
    if failure:
        return failure
    objects = [ModelReference(**item) for item in values["objects"]]
    return execute(lambda client: client.get_properties(objects, values["properties"]))


@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def set_properties(request):
    """Update Teamcenter properties for administrator users."""
    values, failure = validate(SetPropertiesSerializer, request.data)
    if failure:
        return failure
    updates = build_updates(values["updates"])
    return execute(lambda client: client.set_properties(updates))


def build_updates(raw_updates):
    """Convert validated property updates into client models."""
    updates = defaultdict(list)
    for item in raw_updates:
        model = ModelReference(**item["object"])
        for name, values in item["properties"].items():
            updates[model].append(PropertyUpdate.many(name, values))
    return updates
