from django.urls import re_path

from .spa_views import index

urlpatterns = [
    re_path(r"^.*$", index),
]
