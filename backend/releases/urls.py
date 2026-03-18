from django.urls import path
from .views import UnseenReleaseNotesView, MarkSeenView, AcknowledgeView, BulkSeenView

urlpatterns = [
    path("release-notes/unseen", UnseenReleaseNotesView.as_view(), name="release-notes-unseen"),
    path("release-notes/<int:note_id>/seen", MarkSeenView.as_view(), name="release-notes-seen"),
    path("release-notes/bulk-seen", BulkSeenView.as_view(), name="release-notes-bulk-seen"),
    path("release-notes/<int:note_id>/ack", AcknowledgeView.as_view(), name="release-notes-ack"),
]