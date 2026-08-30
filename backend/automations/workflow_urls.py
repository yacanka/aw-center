"""Canonical workflow routes owned by the automation feature."""

from django.urls import include, path

from .workflow_views import (
    cancel_workflow_run,
    workflow_detail,
    workflow_list_create,
    workflow_recipe_list,
)

urlpatterns = [
    path("ecr/", include("automations.ecr_urls")),
    path("", workflow_list_create, name="workflow_list_create"),
    path("recipes/", workflow_recipe_list, name="workflow_recipe_list"),
    path("<uuid:workflow_id>/", workflow_detail, name="workflow_detail"),
    path("<uuid:workflow_id>/cancel/", cancel_workflow_run, name="workflow_cancel"),
]
