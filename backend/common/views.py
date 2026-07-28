from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from awcenter.pagination import StandardResultsSetPagination

from common.compdoc_fields import COMPDOC_TABLE_SCHEMA_VERSION, get_compdoc_field_metadata
from common.compdoc_operational_filters import (
    apply_compdoc_operational_filters,
    apply_compdoc_search,
)
from common.compdoc_permissions import CompDocCollectionPermissions, StrictDjangoModelPermissions
from common.compdoc_table_query import apply_compdoc_table_query
from common.model_query_filters import filtered_queryset
from common.compdoc_versions import (
    object_with_current_history,
    update_versioned_compdoc,
    with_current_history_id,
)


def paginated_response(request, queryset, serializer_class, apply_filters=True):
    """Serialize a queryset using the standard paginated response contract."""

    if apply_filters:
        queryset = filtered_queryset(request, queryset)
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = serializer_class(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)

def history_view_set_factory(model, serializer_class, view_permission_classes):
    class DynamicHistoryViewSet(APIView):
        queryset = model.objects.none()

        def get(self, request, pk):
            obj = get_object_or_404(model, pk=pk)
            obj_history = obj.history.all().order_by("-history_date", "-history_id")
            return paginated_response(request, obj_history, serializer_class)

        permission_classes = [*view_permission_classes, StrictDjangoModelPermissions]

    return DynamicHistoryViewSet

def panel_view_set_factory(model, view_serializer_class, view_permission_classes):
    class DynamicPanelViewSet(ModelViewSet):
        permission_classes = view_permission_classes
        serializer_class = view_serializer_class
        queryset = model.objects.all()

    return DynamicPanelViewSet

def responsible_view_set_factory(model, view_serializer_class, view_permission_classes):
    class DynamicResponsibleViewSet(ModelViewSet):
        permission_classes = view_permission_classes
        serializer_class = view_serializer_class
        queryset = model.objects.all()

        def get_queryset(self):
            qs = model.objects.select_related("panel")

            panel = self.request.query_params.get("panel")
            if panel:
                qs = qs.filter(panel__ata__iexact=panel)

            return qs

    return DynamicResponsibleViewSet


def compdoc_fields_view_factory(model, view_permission_classes):
    class CompDocFieldsView(APIView):
        queryset = model.objects.none()

        def get(self, request):
            return Response(
                {
                    "schema_version": COMPDOC_TABLE_SCHEMA_VERSION,
                    "project": model._meta.app_label,
                    "fields": get_compdoc_field_metadata(model),
                },
                status=status.HTTP_200_OK,
            )

        permission_classes = [*view_permission_classes, StrictDjangoModelPermissions]

    return CompDocFieldsView

def view_set_factory(model, serializer_class, view_permission_classes):
    class DynamicViewSet(APIView):
        queryset = model.objects.none()

        def get(self, request):
            objs = model.objects.select_related("cover_page", "owner", "owner_group")
            archive_filter = request.query_params.get("archived")
            if archive_filter == "true":
                objs = objs.filter(is_archived=True)
            elif archive_filter != "all":
                objs = objs.filter(is_archived=False)
            objs = apply_compdoc_search(objs, request.query_params.get("search"))
            objs = apply_compdoc_operational_filters(request, objs, model)
            objs = with_current_history_id(objs)
            objs = apply_compdoc_table_query(request, objs)
            return paginated_response(request, objs, serializer_class, apply_filters=False)

        def post(self, request):
            serializer = serializer_class(data=request.data, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                serializer.instance.source_history_id = serializer.instance.history.first().history_id
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        def delete(self, request):
            return Response(
                {"detail": "Collection deletion is disabled. Archive selected records instead."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )

        permission_classes = [*view_permission_classes, CompDocCollectionPermissions]

    return DynamicViewSet


def view_set_obj_factory(model, serializer_class, view_permission_classes):
    class DynamicViewSet(APIView):
        queryset = model.objects.none()

        def get(self, request, pk):
            obj = object_with_current_history(model, pk)
            serializer = serializer_class(obj)
            return Response(serializer.data)

        def put(self, request, pk):
            return update_versioned_compdoc(
                request, model, serializer_class, pk, partial=False
            )

        def patch(self, request, pk):
            return update_versioned_compdoc(
                request, model, serializer_class, pk, partial=True
            )

        def delete(self, request, pk):
            obj = get_object_or_404(model, pk=pk)
            serializer = serializer_class(obj)
            obj.is_archived = True
            obj.archived_at = timezone.now()
            obj.archived_by = request.user
            obj.archive_reason = "Archived through the legacy delete action."
            obj._history_user = request.user
            obj._change_reason = "Archived"
            obj.save(update_fields=["is_archived", "archived_at", "archived_by", "archive_reason"])
            return Response(serializer.data, status=status.HTTP_200_OK)

        permission_classes = [*view_permission_classes, StrictDjangoModelPermissions]

    return DynamicViewSet
