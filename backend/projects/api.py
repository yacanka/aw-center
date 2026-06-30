"""Safe API endpoints for project registry metadata."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .registry import PROJECT_DEFINITIONS
from .types import ProjectDefinition

TRUTHY_VALUES = {"1", "true", "yes", "on"}
FALSY_VALUES = {"0", "false", "no", "off"}


def serialize_project_definition(definition: ProjectDefinition) -> dict:
    """Return the frontend-safe project registry contract."""
    return {
        "slug": definition.slug,
        "display_name": definition.display_name,
        "route": f"/{definition.url_prefix}/",
        "enabled": definition.enabled,
        "capabilities": list(definition.capabilities),
        "tags": list(definition.tags),
    }


def parse_enabled_filter(raw_value: str | None) -> bool | None:
    """Return a boolean enabled filter or None when the query is absent."""
    if raw_value is None:
        return None

    normalized_value = raw_value.strip().lower()
    if normalized_value in TRUTHY_VALUES:
        return True
    if normalized_value in FALSY_VALUES:
        return False
    raise ValidationError({"enabled": "Use true or false."})


def get_filtered_project_definitions(request) -> tuple[ProjectDefinition, ...]:
    """Return registry definitions filtered by supported query parameters."""
    capability = request.query_params.get("capability", "").strip().lower()
    enabled = parse_enabled_filter(request.query_params.get("enabled"))
    definitions = PROJECT_DEFINITIONS.values()

    if capability:
        definitions = [item for item in definitions if capability in item.capabilities]
    if enabled is not None:
        definitions = [item for item in definitions if item.enabled is enabled]
    return tuple(definitions)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def project_registry(request):
    """Return frontend-safe project registry entries for authenticated users."""
    definitions = get_filtered_project_definitions(request)
    payload = [serialize_project_definition(definition) for definition in definitions]
    return Response(payload)
