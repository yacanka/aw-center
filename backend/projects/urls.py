from django.urls import path

from .api import project_catalog, project_overview


urlpatterns = [
    path("", project_catalog, name="project-catalog"),
    path("overview/", project_overview, name="project-overview"),
]
