"""Canonical project-scoped DCC record API."""

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.pagination import StandardResultsSetPagination

from .access_policy import (
    VIEWER,
    project_records_for_user,
    require_resource_role,
)
from .workflow_models import JiraTrackedIssue
from .record_services import create_record, delete_record, update_record
from .record_serializers import (
    JiraTrackedIssueMutationSerializer,
    JiraTrackedIssueDeleteSerializer,
    JiraTrackedIssueSerializer,
    JiraTrackedIssueUpdateSerializer,
    JiraTrackedIssueFilterSerializer,
)


class JiraTrackedIssueCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        records = project_records_for_user(request.user)
        filters = JiraTrackedIssueFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        for name, value in filters.validated_data.items():
            lookup = "projects__slug" if name == "project_slug" else f"{name}__icontains"
            records = records.filter(**{lookup: value})
        records = records.order_by("-updated_at", "issue", "id")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(records, request, view=self)
        return paginator.get_paginated_response(JiraTrackedIssueSerializer(page, many=True).data)

    def post(self, request):
        serializer = JiraTrackedIssueMutationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = create_record(request.user, dict(serializer.validated_data))
        return Response(JiraTrackedIssueSerializer(record).data, status=201)


class JiraTrackedIssueDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_record(self, record_id):
        return get_object_or_404(
            JiraTrackedIssue.objects.prefetch_related("projects", "assigned_users"),
            pk=record_id,
        )

    def get(self, request, record_id):
        record = self.get_record(record_id)
        require_resource_role(request.user, record, VIEWER)
        return Response(JiraTrackedIssueSerializer(record).data)

    def put(self, request, record_id):
        return self.mutate(request, record_id, partial=False)

    def patch(self, request, record_id):
        return self.mutate(request, record_id, partial=True)

    def mutate(self, request, record_id, partial):
        serializer_class = JiraTrackedIssueUpdateSerializer
        serializer = serializer_class(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        record = update_record(record_id, request.user, dict(serializer.validated_data))
        return Response(JiraTrackedIssueSerializer(record).data)

    def delete(self, request, record_id):
        serializer = JiraTrackedIssueDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delete_record(record_id, request.user, serializer.validated_data["version"])
        return Response(status=204)
