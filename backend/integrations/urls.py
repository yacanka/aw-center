from django.urls import path

from .api import integration_catalog_view
from .assistant.views import AssistantCatalogView, AssistantChatView
from .jira.views import JiraSessionView


urlpatterns = [
    path("", integration_catalog_view, name="integration-catalog"),
    path("assistant/catalog/", AssistantCatalogView.as_view(), name="assistant-catalog"),
    path("assistant/chat/", AssistantChatView.as_view(), name="assistant-chat"),
    path("jira/session/", JiraSessionView.as_view(), name="jira-session"),
]
