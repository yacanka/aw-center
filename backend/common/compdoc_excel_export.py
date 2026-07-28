"""Styled Excel export generation for project CompDoc models."""

import pandas as pd
from django.conf import settings
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework import serializers

from awcenter.api_errors import error_response
from .compdoc_excel_values import prepare_export_dataframe
from .compdoc_permissions import CompDocExportPermissions
from .compdoc_versions import with_current_history_id
from .compdoc_excel_workbook import write_workbook


def excel_creator_factory(model, serializer_class, view_permission_classes):
    """Return a project-specific CompDoc Excel export API view."""

    class ExcelCreator(APIView):
        """Download the current project CompDocs as a styled workbook."""

        queryset = model.objects.none()
        permission_classes = [*view_permission_classes, CompDocExportPermissions]

        def get(self, request):
            """Build and return one in-memory OOXML workbook."""

            return build_excel_response(model, serializer_class)

        def post(self, request):
            """Export an explicit bounded and current document selection."""

            selection = SelectedExportSerializer(data=request.data)
            selection.is_valid(raise_exception=True)
            documents = selection.validated_data["documents"]
            queryset = with_current_history_id(
                model.objects.filter(
                    pk__in=[item["id"] for item in documents], is_archived=False
                )
            )
            current = {row.pk: row.source_history_id for row in queryset}
            stale = [
                item["id"]
                for item in documents
                if current.get(item["id"]) != item["source_history_id"]
            ]
            if stale:
                return error_response(
                    "One or more selected documents changed.",
                    code="COMPDOC_EXPORT_CONFLICT",
                    response_status=409,
                    errors={"documents": [str(value) for value in stale[:20]]},
                )
            return build_excel_response(model, serializer_class, queryset)

    return ExcelCreator


def build_excel_response(model, serializer_class, queryset=None):
    """Serialize model rows and return a downloadable workbook response."""

    queryset = queryset if queryset is not None else model.objects.filter(is_archived=False)
    row_count = queryset.count()
    row_limit = max(int(settings.AWCENTER_MAX_COMPDOC_EXPORT_ROWS), 1)
    if row_count > row_limit:
        return error_response(
            "The compliance register is too large for a synchronous export.",
            code="COMPDOC_EXPORT_ROW_LIMIT",
            response_status=413,
        )
    serialized_rows = serializer_class(queryset, many=True).data
    dataframe = prepare_export_dataframe(pd.DataFrame(serialized_rows), model)
    return _workbook_response(model, write_workbook(dataframe).getvalue())


class SelectedDocumentSerializer(serializers.Serializer):
    """Validate one selected document version."""

    id = serializers.UUIDField()
    source_history_id = serializers.IntegerField(min_value=1)


class SelectedExportSerializer(serializers.Serializer):
    """Limit selected exports to an explicit safe batch."""

    documents = SelectedDocumentSerializer(many=True, min_length=1, max_length=100)


def _workbook_response(model, content):
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    filename = f"{model._meta.app_label.upper()} Compliance Documents.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
