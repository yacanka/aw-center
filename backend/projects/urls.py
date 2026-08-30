from django.urls import path

from .api import project_catalog


urlpatterns = [path("", project_catalog, name="project-catalog")]
