from django.urls import path, include
from rest_framework.routers import DefaultRouter
from projects.gokbey.orgs.views import PanelViewSet, ResponsibleViewSet

router = DefaultRouter()
router.register("panels", PanelViewSet)
router.register("responsibles", ResponsibleViewSet)

urlpatterns = [
    path('', include(router.urls)),
]