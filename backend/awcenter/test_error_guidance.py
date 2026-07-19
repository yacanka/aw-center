from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from awcenter.api_errors import ApiErrorContractMiddleware, build_error_payload
from awcenter.error_guidance import guidance_for


class UnexpectedFailureView(APIView):
    """Raise an unexpected exception containing data that must stay private."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        """Raise an exception outside DRF's built-in hierarchy."""

        raise RuntimeError("credential-value-must-not-leak")


class ErrorGuidanceTests(SimpleTestCase):
    """Verify safe, actionable recovery metadata for API failures."""

    def test_known_domain_error_has_specific_non_retryable_guidance(self):
        """Deterministic file-policy failures should not encourage blind retries."""

        payload = build_error_payload(
            {"detail": "Too large."}, 400, code="UPLOAD_TOO_LARGE"
        )

        self.assertFalse(payload["retryable"])
        self.assertIn("file size", payload["recovery_hint"])

    def test_transient_status_has_retryable_fallback(self):
        """Unknown server failures should permit one bounded retry."""

        guidance = guidance_for("NEW_BRIDGE_FAILURE", status.HTTP_503_SERVICE_UNAVAILABLE)

        self.assertTrue(guidance.retryable)
        self.assertIn("Retry once", guidance.recovery_hint)

    def test_domain_prefix_covers_new_integration_codes(self):
        """New bridge codes inherit safe guidance before explicit cataloging."""

        guidance = guidance_for("TEAMCENTER_NEW_FAILURE", 400)

        self.assertTrue(guidance.retryable)
        self.assertNotIn("http", guidance.recovery_hint.lower())

    def test_compdoc_import_guidance_points_to_audit_evidence(self):
        """Import failures should direct users to evidence instead of blind retry."""

        guidance = guidance_for("COMPDOC_IMPORT_FAILED", 500)

        self.assertFalse(guidance.retryable)
        self.assertIn("audit", guidance.recovery_hint)

    def test_existing_standard_response_is_enriched_by_middleware(self):
        """Legacy standard payloads gain guidance without changing their detail."""

        response = Response(
            {"detail": "Wait.", "code": "THROTTLED"},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        request = APIRequestFactory().get("/contract/")
        request.request_id = "recovery-123"
        middleware = ApiErrorContractMiddleware(lambda value: response)

        normalized = middleware.process_template_response(request, response)

        self.assertEqual(normalized.data["detail"], "Wait.")
        self.assertTrue(normalized.data["retryable"])
        self.assertEqual(normalized.data["request_id"], "recovery-123")

    def test_guidance_is_bounded_and_contains_no_secret_markers(self):
        """Public hints remain concise and never contain credential material."""

        for code in ("AUTHENTICATION_FAILED", "JIRA_FAILURE", "WORD_MODEL_UNAVAILABLE"):
            hint = guidance_for(code, 400).recovery_hint
            self.assertLessEqual(len(hint), 160)
            self.assertNotIn("password", hint.casefold())
            self.assertNotIn("token", hint.casefold())

    def test_unexpected_exception_returns_sanitized_recovery_contract(self):
        """Unhandled failures never expose exception messages to the browser."""

        request = APIRequestFactory().get("/contract/")
        request.request_id = "unexpected-123"
        with self.assertLogs("awcenter.api_errors", level="ERROR") as captured:
            response = UnexpectedFailureView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data["code"], "INTERNAL_ERROR")
        self.assertTrue(response.data["retryable"])
        self.assertEqual(response.data["request_id"], "unexpected-123")
        self.assertNotIn("credential-value", str(response.data))
        self.assertEqual(captured.records[0].request.request_id, "unexpected-123")
        self.assertNotIn("credential-value", captured.output[0])
