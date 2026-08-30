from django.urls import path

from .ecr_views import (
    ecr_workflow_approve,
    ecr_workflow_collection,
    ecr_workflow_detail,
    ecr_workflow_publish,
    ecr_workflow_preflight,
    ecr_workflow_reject,
    ecr_workflow_resume,
)

urlpatterns = [
    path("", ecr_workflow_collection, name="ecr_workflow_collection"),
    path("<uuid:workflow_id>/", ecr_workflow_detail, name="ecr_workflow_detail"),
    path(
        "<uuid:workflow_id>/preflight/",
        ecr_workflow_preflight,
        name="ecr_workflow_preflight",
    ),
    path(
        "<uuid:workflow_id>/approve/",
        ecr_workflow_approve,
        name="ecr_workflow_approve",
    ),
    path(
        "<uuid:workflow_id>/reject/",
        ecr_workflow_reject,
        name="ecr_workflow_reject",
    ),
    path(
        "<uuid:workflow_id>/publish/",
        ecr_workflow_publish,
        name="ecr_workflow_publish",
    ),
    path(
        "<uuid:workflow_id>/resume/",
        ecr_workflow_resume,
        name="ecr_workflow_resume",
    ),
]
