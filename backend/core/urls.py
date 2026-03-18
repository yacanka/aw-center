from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.views.generic import TemplateView

from .views import index

urlpatterns = [
    re_path(r'^.*$', index),
]
