"""Authenticated, owner-scoped reporting endpoints."""
from itertools import combinations

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from management_reports.access import authorized_projects, project_options
from management_reports.comparison import compare_report
from management_reports.models import ReportSnapshot
from management_reports.serializers import CaptureSerializer
from management_reports.services import build_report, capture_report, report_list_item, scope_key


def _query_projects(request):
    value = request.query_params.get("projects", "")
    return authorized_projects(request.user, value.split(",") if value else [])


def _snapshot(request, pk):
    snapshot = get_object_or_404(ReportSnapshot.objects.filter(owner=request.user), pk=pk)
    authorized_projects(request.user, snapshot.project_slugs)
    return snapshot


def _envelope(request, report, explicit_baseline=False):
    baseline = request.query_params.get("baseline") if explicit_baseline else None
    return {"report": report, "comparison": compare_report(request.user, report, baseline)}


class OptionsView(APIView):
    def get(self, request):
        return Response({"projects": project_options(request.user)})


class OverviewView(APIView):
    def get(self, request):
        return Response(_envelope(request, build_report(_query_projects(request))))


class ReportsPagination(PageNumberPagination):
    page_size = 20


class ReportsView(APIView):
    def get(self, request):
        queryset = ReportSnapshot.objects.filter(owner=request.user)
        if "projects" in request.query_params:
            definitions = _query_projects(request)
            queryset = queryset.filter(scope_key=scope_key([item.slug for item in definitions]))
        else:
            # Registry scopes are bounded. SQL hashes avoid loading unauthorized historical payloads.
            visible = [item["slug"] for item in project_options(request.user)]
            keys = [scope_key(scope) for size in range(1, len(visible) + 1) for scope in combinations(visible, size)]
            queryset = queryset.filter(scope_key__in=keys)
        paginator = ReportsPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([report_list_item(item) for item in page])

    def post(self, request):
        values = CaptureSerializer(data=request.data)
        values.is_valid(raise_exception=True)
        data = values.validated_data
        definitions = authorized_projects(request.user, data["project_slugs"])
        with transaction.atomic():
            snapshot = capture_report(request.user, definitions, data["title"], data["management_note"])
            envelope = _envelope(request, snapshot.payload)
        return Response(envelope, status=201)


class ReportDetailView(APIView):
    def get(self, request, pk):
        return Response(_envelope(request, _snapshot(request, pk).payload, explicit_baseline=True))


class ReportPdfView(APIView):
    def get(self, request, pk):
        report = _envelope(request, _snapshot(request, pk).payload, explicit_baseline=True)
        from management_reports.pdf import build_report_pdf
        content = build_report_pdf(report["report"], report["comparison"])
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="management-report-{pk}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
