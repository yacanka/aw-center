from django.urls import path, include
from projects.hys.compdocs.views import *

urlpatterns = [
    path('', CompDocView.as_view(), name="compdoc"),
    path('<int:pk>/', CompDocObjView.as_view(), name='compdoc_obj'),
    path('upload/', CompDocUpload.as_view(), name="upload"),
    path('excel/', ExcelCreator.as_view(), name="excel_creator"),
    path('<int:pk>/history/', HistoryView.as_view(), name="history")
]