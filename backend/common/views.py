from django.shortcuts import get_object_or_404

from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from awcenter.pagination import StandardResultsSetPagination

from common.compdoc_fields import COMPDOC_TABLE_SCHEMA_VERSION, get_compdoc_field_metadata
from common.compdoc_bulk_delete import delete_compdoc_collection
from common.compdoc_permissions import CompDocCollectionPermissions, StrictDjangoModelPermissions
from common.compdoc_table_query import apply_compdoc_table_query
from common.compdoc_versions import (
    object_with_current_history,
    update_versioned_compdoc,
    with_current_history_id,
)

PAGINATION_QUERY_PARAMETERS = {"page", "page_size"}
TEXT_FIELD_TYPES = {"CharField", "TextField", "EmailField"}


def get_query_values(request, name):
    """Return non-empty query values for DRF or Django requests."""

    query_parameters = getattr(request, "query_params", request.GET)
    values = query_parameters.getlist(name)
    return [value for value in values if value not in (None, "")]


def get_filter_expression(field, values):
    """Build a safe lookup expression for a model field and values."""

    if not values:
        return None
    field_type = field.get_internal_type()
    if len(values) > 1:
        return f"{field.name}__in", values
    if field_type in TEXT_FIELD_TYPES:
        return f"{field.name}__icontains", values[0]
    return field.name, values[0]


def filtered_queryset(request, queryset):
    """Apply safe server-side filters for model-backed list querysets."""

    model = getattr(queryset, "model", None)
    if model is None:
        return queryset

    fields = {field.name: field for field in model._meta.fields}
    for name, field in fields.items():
        if name in PAGINATION_QUERY_PARAMETERS:
            continue
        expression = get_filter_expression(field, get_query_values(request, name))
        if expression:
            queryset = queryset.filter(**{expression[0]: expression[1]})
    return queryset


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
                qs = qs.filter(panel__name__iexact=panel)

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
            objs = with_current_history_id(model.objects.select_related("cover_page"))
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
            return delete_compdoc_collection(request, model)

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
            obj.delete()
            return Response(serializer.data, status=status.HTTP_204_NO_CONTENT)

        permission_classes = [*view_permission_classes, StrictDjangoModelPermissions]

    return DynamicViewSet
