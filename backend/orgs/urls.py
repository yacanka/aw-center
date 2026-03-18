from django.urls import path, include
from rest_framework.routers import DefaultRouter
from orgs.views import ProjectViewSet, PanelViewSet, ResponsibleViewSet, PeopleViewSet, Test, UploadPeople

router = DefaultRouter()
router.register("projects", ProjectViewSet)
router.register("panels", PanelViewSet)
router.register("responsibles", ResponsibleViewSet)
router.register("people", PeopleViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('upload_people/', UploadPeople.as_view()),
    path('test/', Test),
]