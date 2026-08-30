from django.urls import path

from . import views
from .job_views import create_property_update_job

urlpatterns = [
    path("status/", views.status_view, name="teamcenter_status"),
    path("probe/", views.probe, name="teamcenter_probe"),
    path("saved-queries/", views.saved_queries, name="teamcenter_saved_queries"),
    path("saved-queries/execute/", views.execute_saved_query, name="teamcenter_execute_query"),
    path("objects/load/", views.load_objects, name="teamcenter_load_objects"),
    path("objects/properties/", views.get_properties, name="teamcenter_get_properties"),
    path(
        "property-update-jobs/",
        create_property_update_job,
        name="teamcenter_property_update_job",
    ),
]
