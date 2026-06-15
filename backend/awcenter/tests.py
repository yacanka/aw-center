"""Tests for AW Center API error contract enforcement."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from awcenter.pagination import StandardResultsSetPagination
from common.views import filtered_queryset
from awcenter.api_errors import (
    ApiErrorContractMiddleware,
    ErrorCodes,
    error_response,
)


class ContractValidationView(APIView):
    """Test-only view that raises DRF validation errors."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        """Raise a validation error for contract verification."""

        error_detail = serializers.ErrorDetail("Required.", code="required")
        raise ValidationError({"name": [error_detail]})


class ContractNotFoundView(APIView):
    """Test-only view that raises DRF not-found errors."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        """Raise a not-found error for contract verification."""

        raise NotFound("Document was not found.")


class ApiErrorContractTests(TestCase):
    """Verify that backend errors follow the shared API contract."""

    def setUp(self):
        """Create a reusable request factory for API view tests."""

        self.factory = APIRequestFactory()

    def test_validation_error_uses_standard_contract(self):
        """Validation errors include detail, code, and field errors."""

        response = ContractValidationView.as_view()(self.factory.get("/contract/"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Bad Request")
        self.assertEqual(response.data["code"], ErrorCodes.VALIDATION_ERROR)
        self.assertIn("name", response.data["errors"])

    def test_not_found_error_uses_standard_contract(self):
        """Non-validation DRF errors include detail and machine-readable code."""

        response = ContractNotFoundView.as_view()(self.factory.get("/contract/"))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Document was not found.")
        self.assertEqual(response.data["code"], ErrorCodes.NOT_FOUND)
        self.assertNotIn("errors", response.data)

    def test_error_response_helper_uses_standard_contract(self):
        """Manual endpoint errors can use the shared response helper."""

        response = error_response(
            "Upload failed.", ErrorCodes.VALIDATION_ERROR, {"file": ["Invalid."]}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Upload failed.")
        self.assertEqual(response.data["code"], ErrorCodes.VALIDATION_ERROR)
        self.assertEqual(response.data["errors"], {"file": ["Invalid."]})

    def test_middleware_normalizes_manual_message_errors(self):
        """Legacy manual message responses are normalized before rendering."""

        response = error_response("placeholder")
        response.data = {"message": "Legacy failure."}
        middleware = ApiErrorContractMiddleware(lambda request: response)

        normalized = middleware.process_template_response(
            self.factory.get("/contract/"), response
        )

        self.assertEqual(normalized.data["detail"], "Legacy failure.")
        self.assertEqual(normalized.data["code"], ErrorCodes.VALIDATION_ERROR)
        self.assertNotIn("message", normalized.data)

    def test_middleware_normalizes_manual_string_errors(self):
        """Legacy manual string responses are normalized before rendering."""

        response = error_response("placeholder")
        response.data = "Plain failure."
        middleware = ApiErrorContractMiddleware(lambda request: response)

        normalized = middleware.process_template_response(
            self.factory.get("/contract/"), response
        )

        self.assertEqual(normalized.data["detail"], "Plain failure.")
        self.assertEqual(normalized.data["code"], ErrorCodes.VALIDATION_ERROR)


class ContractPaginationView(APIView):
    """Test-only view that returns paginated list data."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        """Return numbers using the standard pagination contract."""

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(list(range(3)), request)
        return paginator.get_paginated_response(page)


class ApiPaginationContractTests(TestCase):
    """Verify that list responses follow the shared pagination contract."""

    def setUp(self):
        """Create a reusable request factory for pagination tests."""

        self.factory = APIRequestFactory()

    def test_standard_pagination_contract_keys(self):
        """Paginated responses include count, next, previous, and results."""

        response = ContractPaginationView.as_view()(self.factory.get("/contract/"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data.keys()),
            {"count", "next", "previous", "results"},
        )
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["results"], [0, 1, 2])


class ServerSideFilterTests(TestCase):
    """Verify safe queryset filtering for paginated list endpoints."""

    def setUp(self):
        """Create model rows and request factory for filter tests."""

        self.factory = APIRequestFactory()
        self.user_model = get_user_model()
        self.user_model.objects.create_user(username="alice", password="secret")
        self.user_model.objects.create_user(username="bob", password="secret")

    def test_filtered_queryset_applies_model_field_filters(self):
        """Allowed model fields are filtered using server-side query params."""

        request = self.factory.get("/users/", {"username": "ali", "page": 1})
        queryset = filtered_queryset(request, self.user_model.objects.all())

        self.assertEqual(list(queryset.values_list("username", flat=True)), ["alice"])

    def test_filtered_queryset_applies_repeated_value_filters(self):
        """Repeated params are converted to safe field __in lookups."""

        request = self.factory.get("/users/", {"username": ["alice", "bob"]})
        queryset = filtered_queryset(request, self.user_model.objects.order_by("username"))

        self.assertEqual(list(queryset.values_list("username", flat=True)), ["alice", "bob"])
