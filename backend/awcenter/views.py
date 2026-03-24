from django.shortcuts import render, redirect
from django.http import FileResponse, Http404
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.utils._os import safe_join

from pathlib import Path

def redirect_to_app(request):
    return redirect("/app/")

def index(request):
    return render(request, "index.html")

def download_file(request, filename):
    try:
        file_path = Path(safe_join(str(settings.MEDIA_ROOT), filename))
    except SuspiciousFileOperation as exc:
        raise Http404("The specified file could not be located on the server") from exc

    if not file_path.is_file():
        raise Http404("The specified file could not be located on the server")

    return FileResponse(file_path.open("rb"), as_attachment=True, filename=file_path.name)
