from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from integrations.assessment import AssessmentServiceError, request_assessment


@override_settings(
    ASSESSMENT_API_URL="https://assessment.internal.example/ask",
    ASSESSMENT_API_ALLOWED_HOSTS=["assessment.internal.example"],
    ASSESSMENT_API_CONNECT_TIMEOUT_SECONDS=3,
    ASSESSMENT_API_READ_TIMEOUT_SECONDS=20,
    ASSESSMENT_API_MAX_RESPONSE_BYTES=4096,
)
class AssessmentClientTests(SimpleTestCase):
    """Verify assessment traffic is bounded and restricted to explicit HTTPS hosts."""

    @override_settings(ASSESSMENT_API_URL="http://assessment.internal.example/ask")
    def test_plain_http_configuration_is_rejected_before_network_access(self):
        with patch("integrations.assessment.requests.post") as post:
            with self.assertRaises(AssessmentServiceError) as raised:
                request_assessment({"question": "safe"})

        self.assertEqual(raised.exception.code, "ASSESSMENT_CONFIGURATION_ERROR")
        post.assert_not_called()

    @override_settings(ASSESSMENT_API_URL="https://unexpected.example/ask")
    def test_unallowlisted_host_is_rejected_before_network_access(self):
        with patch("integrations.assessment.requests.post") as post:
            with self.assertRaises(AssessmentServiceError) as raised:
                request_assessment({"question": "safe"})

        self.assertEqual(raised.exception.code, "ASSESSMENT_CONFIGURATION_ERROR")
        post.assert_not_called()

    @patch("integrations.assessment.requests.post")
    def test_request_uses_streaming_and_explicit_timeouts(self, post):
        response = Mock(status_code=200)
        response.iter_content.return_value = [b"first\n", b"second\n"]
        post.return_value.__enter__.return_value = response

        result = request_assessment({"question": "safe"})

        self.assertEqual(result, ["first", "second"])
        post.assert_called_once_with(
            "https://assessment.internal.example/ask",
            json={"question": "safe"},
            headers={
                "Accept": "text/plain",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=(3.0, 20.0),
            stream=True,
            allow_redirects=False,
        )

    @patch(
        "integrations.assessment.requests.post",
        side_effect=requests.Timeout("internal connection detail"),
    )
    def test_network_failures_expose_only_sanitized_error(self, _post):
        with self.assertRaises(AssessmentServiceError) as raised:
            request_assessment({"question": "safe"})

        self.assertEqual(raised.exception.code, "ASSESSMENT_UNAVAILABLE")
        self.assertNotIn("internal connection detail", raised.exception.detail)

    @override_settings(ASSESSMENT_API_MAX_RESPONSE_BYTES=1024)
    @patch("integrations.assessment.requests.post")
    def test_oversized_response_is_rejected(self, post):
        response = Mock(status_code=200)
        response.iter_content.return_value = [b"x" * 1025]
        post.return_value.__enter__.return_value = response

        with self.assertRaises(AssessmentServiceError) as raised:
            request_assessment({"question": "safe"})

        self.assertEqual(raised.exception.code, "ASSESSMENT_RESPONSE_INVALID")
