from django.shortcuts import render, redirect
from django.http import HttpResponse, FileResponse, Http404
from django.conf import settings

import os

def redirect_to_app(request):
    return redirect("/app/")

def index(request):
    return render(request, "index.html")

def download_file(request, filename):
    file_path =  os.path.join(settings.MEDIA_ROOT, filename)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)
    else:
        raise Http404("The specified file could not be located on the server")