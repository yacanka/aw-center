"""Shared DRF pagination settings for list endpoints."""

from rest_framework.pagination import PageNumberPagination

from .query_filters import filtered_queryset


class StandardResultsSetPagination(PageNumberPagination):
    """Return DRF-compatible paginated responses with bounded page sizes."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def paginated_response(request, queryset, serializer_class, *, apply_filters=True):
    """Return the repository-wide bounded pagination envelope."""

    if apply_filters:
        queryset = filtered_queryset(request, queryset)
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = serializer_class(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)
