from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from .views import redirect_to_app, download_file, index

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', redirect_to_app),
    path('app/', include('core.urls')),
    path('dcc/', include('dcc.urls')),
    path('auth/', include('users.urls')),
    path('ozgur/', include('projects.ozgur.urls')),
    path('piku/', include('projects.piku.urls')),
    path('aesa/', include('projects.aesa.urls')),
    path('havasoj/', include('projects.havasoj.urls')),
    path('hys/', include('projects.hys.urls')),
    path('blok30/', include('projects.blok30.urls')),
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
    path('download/<str:filename>/', download_file, name='download_file')
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)