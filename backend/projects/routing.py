"""URL routing helpers for registered project applications."""

from django.urls import include, path
from django.urls.resolvers import URLPattern

from .registry import get_enabled_project_definitions


def get_project_urlpatterns() -> list[URLPattern]:
    """Return URL patterns for enabled project applications only."""
    return [
        path(f"{definition.url_prefix}/", include(f"{definition.app_label}.urls"))
        for definition in get_enabled_project_definitions()
    ]
