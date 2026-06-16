"""Shared DRF pagination settings for list endpoints."""

from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Return DRF-compatible paginated responses with bounded page sizes."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
