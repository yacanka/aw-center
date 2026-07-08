from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from projects.routing import get_project_urlpatterns

from .views import download_file, health_live, health_ready, redirect_to_app

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/live/', health_live, name='health_live'),
    path('health/ready/', health_ready, name='health_ready'),
    path('', redirect_to_app),
    path('app/', include('core.urls')),
    path('dcc/', include('dcc.urls')),
    path('auth/', include('users.urls')),
    path('doors/', include('doors.urls')),
    path('ddf/', include('ddf.urls')),
    path('docproof/', include('docproof.urls')),
    path('excel/', include('excel.urls')),
    path('word/', include('word.urls')),
    path('pdf/', include('pdf.urls')),
    path('orgs/', include('orgs.urls')),
    path('outlook/', include('outlook.urls')),
    path('releases/', include('releases.urls')),
    path('pptxgallery/', include('pptxgallery.urls')),
    path('media-tools/', include('media_tools.urls')),
    path('projects/', include('projects.urls')),
    path('download/<str:filename>/', download_file, name='download_file'),
    *get_project_urlpatterns(),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
