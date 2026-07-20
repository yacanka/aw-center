from django.urls import path
from .job_views import create_word_attachment_extraction_job
from .views import MsgParseView, MsgDownloadAttachmentView

urlpatterns = [
    path(
        "jobs/extract-word-attachment/",
        create_word_attachment_extraction_job,
        name="extract-word-attachment-job",
    ),
    path("msg/parse/", MsgParseView.as_view(), name="msg-parse"),
    path("msg/download/", MsgDownloadAttachmentView.as_view(), name="msg-download"),
]
