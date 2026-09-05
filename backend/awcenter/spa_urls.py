from django.urls import path, re_path

from .pwa_resources import PWA_RESOURCES
from .spa_views import index, pwa_resource

urlpatterns = [
    *[
        path(resource_name, pwa_resource, {"resource_name": resource_name})
        for resource_name in PWA_RESOURCES
    ],
    re_path(r"^.*$", index),
]
