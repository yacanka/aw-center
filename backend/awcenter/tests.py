"""Tests for AW Center API error contract enforcement."""

from django.test import TestCase
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

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
