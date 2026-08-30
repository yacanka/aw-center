from django.shortcuts import redirect
from django.http import JsonResponse
from django.core.cache import cache
from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from awcenter.frontend_artifact import frontend_files_are_ready


def redirect_to_app(request):
    """Redirect root requests to the Vue application shell."""
    return redirect("/app/")


@api_view(["GET"])
@permission_classes([AllowAny])
def health_live(request):
    """Return a liveness response when Django can serve requests."""
    return JsonResponse({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def health_ready(request):
    """Return readiness after checking database and cache dependencies."""
    checks = {
        "database": _database_is_ready(),
        "cache": _cache_is_ready(),
        "frontend": frontend_files_are_ready(),
    }
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
