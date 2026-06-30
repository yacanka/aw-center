"""API routes for project registry metadata."""

from django.urls import path

from .api import project_registry

urlpatterns = [
    path("registry/", project_registry, name="projects_registry"),
]
