from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PanelViewSet,
    PersonViewSet,
    ResponsibleAssignmentViewSet,
    UploadPeople,
)


router = DefaultRouter()
router.register("panels", PanelViewSet, basename="project-panels")
router.register(
    "responsible-assignments",
    ResponsibleAssignmentViewSet,
    basename="project-responsible-assignments",
)
router.register("people", PersonViewSet, basename="project-people")

urlpatterns = [
    path("people/import/", UploadPeople.as_view(), name="project-people-import"),
    path("", include(router.urls)),
]
