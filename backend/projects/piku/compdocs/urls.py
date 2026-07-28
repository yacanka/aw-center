from django.urls import path
from projects.piku.compdocs.views import *

urlpatterns = [
    path('', CompDocView.as_view(), name="compdoc"),
    path('fields/', CompDocFields.as_view(), name="compdoc_fields"),
    path('dashboard/', CompDocDashboard.as_view(), name="compdoc_dashboard"),
    path('notification-policy/', CompDocNotificationPolicy.as_view(), name="compdoc_notification_policy"),
    path('assignees/', CompDocAssignees.as_view(), name="compdoc_assignees"),
    path('bulk/', CompDocBulk.as_view(), name="compdoc_bulk"),
    path('<uuid:pk>/tracking/', CompDocTracking.as_view(), name="compdoc_tracking"),
    path('<uuid:pk>/transitions/', CompDocTransition.as_view(), name="compdoc_transition"),
    path('<uuid:pk>/work/', CompDocWork.as_view(), name="compdoc_work"),
    path('<uuid:pk>/activity/', CompDocActivity.as_view(), name="compdoc_activity"),
    path('<uuid:pk>/archive/', CompDocArchive.as_view(), name="compdoc_archive"),
    path('<uuid:pk>/restore/', CompDocRestore.as_view(), name="compdoc_restore"),
    path('<uuid:pk>/reviews/', CompDocReviews.as_view(), name="compdoc_reviews"),
    path('<uuid:pk>/reviews/<uuid:review_id>/decision/', CompDocReviewDecision.as_view(), name="compdoc_review_decision"),
    path('<uuid:pk>/docproof/', CompDocDocProof.as_view(), name="compdoc_docproof"),
    path('<uuid:pk>/notifications/', CompDocNotification.as_view(), name="compdoc_notification"),
    path('<uuid:pk>/notifications/draft/', CompDocNotificationDraft.as_view(), name="compdoc_notification_draft"),
    path('<uuid:pk>/', CompDocObjView.as_view(), name='compdoc_obj'),
    path('upload/', CompDocUpload.as_view(), name="upload"),
    path('excel/', ExcelCreator.as_view(), name="excel_creator"),
    path('<uuid:pk>/history/', HistoryView.as_view(), name="history")
]
