from django.urls import path

from .views import (
    cancel_job, create_job_handoff, download_job_output, job_detail, job_list, job_system_status,
    retry_failed_job,
)
from .workflow_views import (
    cancel_workflow_run, workflow_detail, workflow_list_create, workflow_recipe_list,
)

urlpatterns = [
    path("", job_list, name="job_list"),
    path("system/", job_system_status, name="job_system_status"),
    path("workflows/recipes/", workflow_recipe_list, name="workflow_recipe_list"),
    path("workflows/", workflow_list_create, name="workflow_list_create"),
    path("workflows/<uuid:workflow_id>/", workflow_detail, name="workflow_detail"),
    path(
        "workflows/<uuid:workflow_id>/cancel/", cancel_workflow_run,
        name="workflow_cancel",
    ),
    path("<uuid:job_id>/", job_detail, name="job_detail"),
    path("<uuid:job_id>/cancel/", cancel_job, name="job_cancel"),
    path("<uuid:job_id>/retry/", retry_failed_job, name="job_retry"),
    path("<uuid:job_id>/handoffs/<slug:handoff_id>/", create_job_handoff, name="job_handoff"),
    path("<uuid:job_id>/download/", download_job_output, name="job_download"),
]
