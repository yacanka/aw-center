from django.urls import include, path

from .api import integration_catalog_view
from .assistant.views import AssistantCatalogView, AssistantChatView


urlpatterns = [
    path("", integration_catalog_view, name="integration-catalog"),
    path("assistant/catalog/", AssistantCatalogView.as_view(), name="assistant-catalog"),
    path("assistant/chat/", AssistantChatView.as_view(), name="assistant-chat"),
    path("jira/", include("integrations.jira.urls")),
]
