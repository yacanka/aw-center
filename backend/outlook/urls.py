from django.urls import path
from .views import MsgParseView, MsgDownloadAttachmentView

urlpatterns = [
    path("msg/parse/", MsgParseView.as_view(), name="msg-parse"),
    path("msg/download/", MsgDownloadAttachmentView.as_view(), name="msg-download"),
]
