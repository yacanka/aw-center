from django.conf import settings
from django.http import FileResponse, Http404
from django.utils._os import safe_join


def index(request):
    """Serve the Vite-built SPA shell directly from the configured dist directory."""
    index_path = safe_join(str(settings.FRONTEND_DIST_DIR), "index.html")

    try:
        return FileResponse(open(index_path, "rb"), content_type="text/html")
    except FileNotFoundError as exc:
        raise Http404("Frontend build output is not available. Run npm run build.") from exc
