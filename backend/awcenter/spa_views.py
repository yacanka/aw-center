from django.conf import settings
from django.http import FileResponse, Http404
from django.utils._os import safe_join

from .pwa_resources import PWA_RESOURCES


def index(request):
    """Serve the Vite-built SPA shell directly from the configured dist directory."""
    index_path = safe_join(str(settings.FRONTEND_DIST_DIR), "index.html")

    try:
        return FileResponse(open(index_path, "rb"), content_type="text/html")
    except FileNotFoundError as exc:
        raise Http404("Frontend build output is not available. Run npm run build.") from exc


def pwa_resource(request, resource_name):
    """Serve only allowlisted PWA resources from the immutable frontend artifact."""

    content_type = PWA_RESOURCES.get(resource_name)
    if content_type is None:
        raise Http404("PWA resource is not available.")
    resource_path = safe_join(str(settings.FRONTEND_DIST_DIR), "app", resource_name)

    try:
        response = FileResponse(open(resource_path, "rb"), content_type=content_type)
    except FileNotFoundError as exc:
        raise Http404("PWA resource is not available.") from exc
    response["Cache-Control"] = "no-cache"
    return response
