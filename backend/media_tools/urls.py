from django.urls import path

from .views import convert_media, preview_media

urlpatterns = [
    path("preview/", preview_media, name="media_preview"),
    path("convert/", convert_media, name="media_convert"),
]
