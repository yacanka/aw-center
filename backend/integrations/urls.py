from django.urls import path

from .api import integration_catalog_view
from .jira.views import JiraSessionView


urlpatterns = [
    path("", integration_catalog_view, name="integration-catalog"),
    path("jira/session/", JiraSessionView.as_view(), name="jira-session"),
]
