from django.shortcuts import render, redirect
from django.http import FileResponse, Http404, JsonResponse
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.cache import cache
from django.db import connection
from django.utils._os import safe_join
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from pathlib import Path

from awcenter.integration_hub import integration_catalog
from awcenter.integration_probes import claim_refresh_slot, probe_catalog


def redirect_to_app(request):
    """Redirect root requests to the Vue application shell."""
    return redirect("/app/")


def index(request):
    """Render the Vue application shell."""
    return render(request, "index.html")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_file(request, filename):
    """Download a media file by safe filename from MEDIA_ROOT."""
    try:
        file_path = Path(safe_join(str(settings.MEDIA_ROOT), filename))
    except SuspiciousFileOperation as exc:
        raise Http404("The specified file could not be located on the server") from exc

    if not file_path.is_file():
        raise Http404("The specified file could not be located on the server")

    return FileResponse(file_path.open("rb"), as_attachment=True, filename=file_path.name)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integrations(request):
    """Return the non-secret integration capability and readiness catalog."""

    catalog = integration_catalog()
    if request.query_params.get("probe") == "true":
        refresh_requested = request.query_params.get("refresh") == "true"
        refresh = refresh_requested and claim_refresh_slot(request.user.pk)
        catalog = probe_catalog(catalog, refresh=refresh)
    return Response({"integrations": catalog})


@api_view(["GET"])
@permission_classes([AllowAny])
def health_live(request):
    """Return a liveness response when Django can serve requests."""
    return JsonResponse({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def health_ready(request):
    """Return readiness after checking database and cache dependencies."""
    checks = {"database": _database_is_ready(), "cache": _cache_is_ready()}
    response_status = 200 if all(checks.values()) else 503
    response_data = {
        "status": "ok" if response_status == 200 else "error",
        "checks": checks,
    }
    return JsonResponse(response_data, status=response_status)


def _database_is_ready():
    try:
        connection.ensure_connection()
        return True
    except Exception:
        return False


def _cache_is_ready():
    try:
        cache.set("health-ready", "ok", timeout=5)
        return cache.get("health-ready") == "ok"
    except Exception:
        return False
