"""Authenticated HTTP surface for non-secret integration capability status."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .catalog import integration_catalog
from .probes import claim_refresh_slot, probe_catalog


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_catalog_view(request):
    """Return configured capabilities and optionally bounded live observations."""

    catalog = integration_catalog()
    if request.query_params.get("probe") == "true":
        refresh_requested = request.query_params.get("refresh") == "true"
        refresh = refresh_requested and claim_refresh_slot(request.user.pk)
        catalog = probe_catalog(catalog, refresh=refresh)
    return Response({"integrations": catalog})
