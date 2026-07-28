from django.urls import path
from projects.blok30.compdocs.views import *

urlpatterns = [
    path('', CompDocView.as_view(), name="compdoc"),
    path('fields/', CompDocFields.as_view(), name="compdoc_fields"),
    path('dashboard/', CompDocDashboard.as_view(), name="compdoc_dashboard"),
    path('notification-policy/', CompDocNotificationPolicy.as_view(), name="compdoc_notification_policy"),
    path('<uuid:pk>/tracking/', CompDocTracking.as_view(), name="compdoc_tracking"),
    path('<uuid:pk>/docproof/', CompDocDocProof.as_view(), name="compdoc_docproof"),
    path('<uuid:pk>/notifications/', CompDocNotification.as_view(), name="compdoc_notification"),
    path('<uuid:pk>/notifications/draft/', CompDocNotificationDraft.as_view(), name="compdoc_notification_draft"),
    path('<uuid:pk>/', CompDocObjView.as_view(), name='compdoc_obj'),
    path('upload/', CompDocUpload.as_view(), name="upload"),
    path('excel/', ExcelCreator.as_view(), name="excel_creator"),
    path('<uuid:pk>/history/', HistoryView.as_view(), name="history")
]
