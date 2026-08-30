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
from .models import DccRecord
from .record_services import create_record, delete_record, update_record
from .serializers import (
    DccRecordMutationSerializer,
    DccRecordDeleteSerializer,
    DccRecordSerializer,
    DccRecordUpdateSerializer,
)


class DccRecordCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        records = project_records_for_user(request.user)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(records, request, view=self)
        return paginator.get_paginated_response(DccRecordSerializer(page, many=True).data)

    def post(self, request):
        serializer = DccRecordMutationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = create_record(request.user, dict(serializer.validated_data))
        return Response(DccRecordSerializer(record).data, status=201)


class DccRecordDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_record(self, record_id):
        return get_object_or_404(
            DccRecord.objects.prefetch_related("projects", "assigned_users"),
            pk=record_id,
        )

    def get(self, request, record_id):
        record = self.get_record(record_id)
        require_resource_role(request.user, record, VIEWER)
        return Response(DccRecordSerializer(record).data)

    def put(self, request, record_id):
        return self.mutate(request, record_id, partial=False)

    def patch(self, request, record_id):
        return self.mutate(request, record_id, partial=True)

    def mutate(self, request, record_id, partial):
        serializer_class = DccRecordUpdateSerializer
        serializer = serializer_class(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        record = update_record(record_id, request.user, dict(serializer.validated_data))
        return Response(DccRecordSerializer(record).data)

    def delete(self, request, record_id):
        serializer = DccRecordDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delete_record(record_id, request.user, serializer.validated_data["version"])
        return Response(status=204)
