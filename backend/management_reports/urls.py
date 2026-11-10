from django.urls import path

from management_reports.views import OptionsView, OverviewView, ReportDetailView, ReportPdfView, ReportsView

urlpatterns = [
    path("options/", OptionsView.as_view(), name="management-report-options"),
    path("overview/", OverviewView.as_view(), name="management-report-overview"),
    path("reports/", ReportsView.as_view(), name="management-reports"),
    path("reports/<uuid:pk>/", ReportDetailView.as_view(), name="management-report-detail"),
    path("reports/<uuid:pk>/pdf/", ReportPdfView.as_view(), name="management-report-pdf"),
]
