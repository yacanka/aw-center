"""Dedicated internal HTTPS routes used only by mTLS Windows agents."""

from django.urls import path

from .api import agent_status, claim, complete, download_input, heartbeat

urlpatterns = [
    path("status/", agent_status, name="windows_bridge_status"),
    path("claims/", claim, name="windows_bridge_claim"),
    path("jobs/<uuid:job_id>/input/", download_input, name="windows_bridge_input"),
    path("jobs/<uuid:job_id>/heartbeat/", heartbeat, name="windows_bridge_heartbeat"),
    path("jobs/<uuid:job_id>/complete/", complete, name="windows_bridge_complete"),
]
