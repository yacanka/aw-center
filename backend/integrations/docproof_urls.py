"""URL routes for DocProof integration endpoints."""

from django.urls import path

from . import docproof_views

urlpatterns = [
    path("search/", docproof_views.search, name="search"),
]
