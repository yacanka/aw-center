from django.urls import path

from .views import (
    cancel_job, download_job_output, job_detail, job_list, job_system_status, retry_failed_job,
)

urlpatterns = [
    path("", job_list, name="job_list"),
    path("system/", job_system_status, name="job_system_status"),
    path("<uuid:job_id>/", job_detail, name="job_detail"),
    path("<uuid:job_id>/cancel/", cancel_job, name="job_cancel"),
    path("<uuid:job_id>/retry/", retry_failed_job, name="job_retry"),
    path("<uuid:job_id>/download/", download_job_output, name="job_download"),
]
