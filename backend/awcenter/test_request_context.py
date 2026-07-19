"""Tests for request correlation across responses, errors, and logs."""

import json
import logging

from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase
from rest_framework.exceptions import NotFound
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from awcenter.api_errors import ApiErrorContractMiddleware, error_response
from awcenter.request_context import (
    REQUEST_ID_HEADER,
    RequestCorrelationMiddleware,
    RequestIdLogFilter,
    get_request_id,
)


class CorrelatedNotFoundView(APIView):
    """Test-only API view that exposes the standard exception path."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        """Raise a not-found error for correlation verification."""

        raise NotFound("Missing.")


class RequestCorrelationTests(SimpleTestCase):
    """Verify request identifiers remain safe and consistent."""

    def setUp(self):
        """Create reusable Django and DRF request factories."""

        self.factory = RequestFactory()
        self.api_factory = APIRequestFactory()

    def test_middleware_generates_response_identifier_and_clears_context(self):
        """Generated identifiers reach the response without leaking afterward."""

        middleware = RequestCorrelationMiddleware(self._context_response)
        response = middleware(self.factory.get("/health/live/"))

        response_data = json.loads(response.content)
        self.assertEqual(response[REQUEST_ID_HEADER], response_data["request_id"])
        self.assertEqual(get_request_id(), "-")

    def test_middleware_accepts_safe_caller_identifier(self):
        """A safe upstream identifier is preserved for distributed tracing."""

        middleware = RequestCorrelationMiddleware(lambda request: JsonResponse({}))
        response = middleware(
            self.factory.get("/", headers={REQUEST_ID_HEADER: "edge-123"})
        )

        self.assertEqual(response[REQUEST_ID_HEADER], "edge-123")

    def test_middleware_replaces_unsafe_caller_identifier(self):
        """Control characters and oversized values cannot enter application logs."""

        middleware = RequestCorrelationMiddleware(lambda request: JsonResponse({}))
        response = middleware(
            self.factory.get("/", headers={REQUEST_ID_HEADER: "unsafe value"})
        )

        self.assertNotEqual(response[REQUEST_ID_HEADER], "unsafe value")
        self.assertEqual(len(response[REQUEST_ID_HEADER]), 32)

    def test_exception_contract_includes_request_identifier(self):
        """DRF exceptions expose the identifier users can report to support."""

        request = self.api_factory.get("/contract/")
        request.request_id = "support-456"
        response = CorrelatedNotFoundView.as_view()(request)

        self.assertEqual(response.data["request_id"], "support-456")

    def test_manual_error_contract_includes_request_identifier(self):
        """Legacy manual responses receive the same correlation field."""

        request = self.api_factory.get("/contract/")
        request.request_id = "support-789"
        response = error_response("Failure.")
        middleware = ApiErrorContractMiddleware(lambda inner_request: response)

        normalized = middleware.process_template_response(request, response)

        self.assertEqual(normalized.data["request_id"], "support-789")

    def test_log_filter_uses_placeholder_outside_request(self):
        """Background logs remain formatter-safe without request context."""

        record = logging.LogRecord("test", logging.INFO, "", 0, "ok", (), None)

        self.assertTrue(RequestIdLogFilter().filter(record))
        self.assertEqual(record.request_id, "-")

    def test_log_filter_recovers_identifier_from_completed_request(self):
        """Django response logs retain correlation after context cleanup."""

        record = logging.LogRecord("test", logging.INFO, "", 0, "ok", (), None)
        record.request = self.factory.get("/")
        record.request.request_id = "completed-123"

        self.assertTrue(RequestIdLogFilter().filter(record))
        self.assertEqual(record.request_id, "completed-123")

    @staticmethod
    def _context_response(request):
        """Return the current request identifier from inside middleware."""

        return JsonResponse({"request_id": get_request_id()})
