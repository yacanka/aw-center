from django.urls import path

from .views import create_media_job, preview_media

urlpatterns = [
    path("preview/", preview_media, name="media_preview"),
    path("jobs/", create_media_job, name="media_job_create"),
]
