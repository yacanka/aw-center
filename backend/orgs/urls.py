from django.urls import path, include
from rest_framework.routers import DefaultRouter
from orgs.views import PanelViewSet, ResponsibleViewSet, PeopleViewSet, UploadPeople
from projects.api import project_registry

router = DefaultRouter()
router.register("panels", PanelViewSet)
router.register("responsibles", ResponsibleViewSet)
router.register("people", PeopleViewSet)

urlpatterns = [
    path('projects/', project_registry, name='registered-projects'),
    path('', include(router.urls)),
    path('upload_people/', UploadPeople.as_view()),
]
