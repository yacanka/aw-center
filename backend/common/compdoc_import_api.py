"""Permission-protected CompDoc import audit APIs."""

from django.db.models import Q
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.pagination import StandardResultsSetPagination
from projects.registry import PROJECT_DEFINITIONS

from .compdoc_import_report import build_import_audit_report
from .models import CompDocImportAudit


class CanViewCompDocImportAudit(BasePermission):
    """Require explicit access to compliance import audit records."""

    def has_permission(self, request, view):
        """Return whether the authenticated caller owns the model permission."""

        return request.user.has_perm("common.view_compdocimportaudit")


class CompDocImportAuditQuerySerializer(serializers.Serializer):
    """Validate bounded audit ledger filters."""

    project = serializers.ChoiceField(required=False, choices=tuple(PROJECT_DEFINITIONS))
    status = serializers.ChoiceField(
        required=False,
        choices=tuple(value for value, _ in CompDocImportAudit.Status.choices),
    )
    search = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CompDocImportAuditListSerializer(serializers.ModelSerializer):
    """Expose compact audit lifecycle data without file contents or token material."""

    class Meta:
        model = CompDocImportAudit
        fields = (
            "id",
            "project_slug",
            "source_filename",
            "imported_by_username",
            "status",
            "total_rows",
            "created_count",
            "updated_count",
            "unchanged_count",
            "rejected_count",
            "started_at",
            "completed_at",
            "duration_ms",
        )


class CompDocImportAuditDetailSerializer(CompDocImportAuditListSerializer):
    """Expose safe mapping and row-error details for one audit."""

    class Meta(CompDocImportAuditListSerializer.Meta):
        fields = CompDocImportAuditListSerializer.Meta.fields + (
            "source_size",
            "source_sha256",
            "request_id",
            "header_row",
            "mapped_columns",
            "unmapped_columns",
            "missing_columns",
            "error_summary",
        )


class CompDocImportAuditCollectionView(APIView):
    """Return a filtered, paginated import audit ledger."""

    permission_classes = [IsAuthenticated, CanViewCompDocImportAudit]

    def get(self, request):
        """List audit records using validated query filters."""

        query = CompDocImportAuditQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        queryset = filtered_audit_queryset(query.validated_data)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CompDocImportAuditListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CompDocImportAuditDetailView(APIView):
    """Return sanitized evidence for one import audit."""

    permission_classes = [IsAuthenticated, CanViewCompDocImportAudit]

    def get(self, request, audit_id):
        """Return one authorized audit record by UUID."""

        audit = get_object_or_404(CompDocImportAudit, pk=audit_id)
        return Response(CompDocImportAuditDetailSerializer(audit).data)


class CompDocImportAuditReportView(APIView):
    """Download sanitized remediation evidence for one import audit."""

    permission_classes = [IsAuthenticated, CanViewCompDocImportAudit]

    def get(self, request, audit_id):
        """Return a formula-safe workbook for one authorized audit record."""

        audit = get_object_or_404(CompDocImportAudit, pk=audit_id)
        return build_import_audit_report(audit)


def filtered_audit_queryset(filters):
    """Build an optimized audit queryset from validated filters."""

    queryset = CompDocImportAudit.objects.all()
    if filters.get("project"):
        queryset = queryset.filter(project_slug=filters["project"])
    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    return filter_audit_search(queryset, filters.get("search"))


def filter_audit_search(queryset, search):
    """Search bounded, non-secret audit identity fields."""

    value = (search or "").strip()
    if not value:
        return queryset
    return queryset.filter(
        Q(source_filename__icontains=value) | Q(imported_by_username__icontains=value)
    )
