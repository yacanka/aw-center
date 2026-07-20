from django.urls import path, include
from projects.gokbey.compdocs.views import *

urlpatterns = [
    path('', CompDocView.as_view(), name="compdoc"),
    path('fields/', CompDocFields.as_view(), name="compdoc_fields"),
    path('<uuid:pk>/', CompDocObjView.as_view(), name='compdoc_obj'),
    path('upload/', CompDocUpload.as_view(), name="upload"),
    path('excel/', ExcelCreator.as_view(), name="excel_creator"),
    path('<uuid:pk>/history/', HistoryView.as_view(), name="history")
]
