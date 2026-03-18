from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PresentationViewSet, SlideViewSet

router = DefaultRouter()
router.register(r"presentations", PresentationViewSet, basename="presentations")
router.register(r"slides", SlideViewSet, basename="slides")

urlpatterns = [
    path("", include(router.urls)),
]