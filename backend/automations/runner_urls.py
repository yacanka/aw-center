"""Internal routes used only by the host-local DOORS runner."""

from django.urls import path

from .api import claim, complete, download_input, heartbeat, runner_status_view

urlpatterns = [
    path("status/", runner_status_view, name="doors_runner_status"),
    path("claims/", claim, name="doors_runner_claim"),
    path("jobs/<uuid:job_id>/input/", download_input, name="doors_runner_input"),
    path("jobs/<uuid:job_id>/heartbeat/", heartbeat, name="doors_runner_heartbeat"),
    path("jobs/<uuid:job_id>/complete/", complete, name="doors_runner_complete"),
]
