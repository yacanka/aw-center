import json

from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from integrations.assessment import AssessmentServiceError, request_assessment
from integrations.ai import client as ai_client
from integrations.ai.contracts import AIServiceError


@override_settings(
    ASSESSMENT_API_URL="https://assessment.internal.example/api/chat/completions",
    ASSESSMENT_API_MODEL_ID="test-model",
    ASSESSMENT_API_TOKEN="test-only-token",
    ASSESSMENT_API_ALLOWED_HOSTS=["assessment.internal.example"],
    ASSESSMENT_API_CONNECT_TIMEOUT_SECONDS=3,
    ASSESSMENT_API_READ_TIMEOUT_SECONDS=20,
    ASSESSMENT_API_MAX_RESPONSE_BYTES=4096,
)
class AssessmentClientTests(SimpleTestCase):
    """Verify assessment traffic is bounded and restricted to explicit HTTPS hosts."""

    @override_settings(ASSESSMENT_API_URL="http://assessment.internal.example/ask")
    def test_plain_http_configuration_is_rejected_before_network_access(self):
        with patch("integrations.ai.transport.requests.post") as post:
            with self.assertRaises(AssessmentServiceError) as raised:
                request_assessment("safe")

        self.assertEqual(raised.exception.code, "ASSESSMENT_CONFIGURATION_ERROR")
        post.assert_not_called()

    @override_settings(ASSESSMENT_API_URL="https://unexpected.example/ask")
    def test_unallowlisted_host_is_rejected_before_network_access(self):
        with patch("integrations.ai.transport.requests.post") as post:
            with self.assertRaises(AssessmentServiceError) as raised:
                request_assessment("safe")

        self.assertEqual(raised.exception.code, "ASSESSMENT_CONFIGURATION_ERROR")
        post.assert_not_called()

    @patch("integrations.ai.transport.requests.post")
    def test_chat_request_uses_bounded_transport_and_explicit_timeouts(self, post):
        response = Mock(status_code=200, headers={"Content-Type": "application/json"})
        response.iter_content.return_value = [json.dumps({"choices": [{"message": {"content": "first\nsecond"}}]}).encode()]
        post.return_value.__enter__.return_value = response

        result = request_assessment("safe")

        self.assertEqual(result, "first\nsecond")
        post.assert_called_once_with(
            "https://assessment.internal.example/api/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "safe"}], "stream": False},
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer test-only-token",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=(3.0, 20.0),
            stream=True,
            allow_redirects=False,
        )

    @patch(
        "integrations.ai.transport.requests.post",
        side_effect=requests.Timeout("internal connection detail"),
    )
    def test_network_failures_expose_only_sanitized_error(self, _post):
        with self.assertRaises(AssessmentServiceError) as raised:
            request_assessment("safe")

        self.assertEqual(raised.exception.code, "ASSESSMENT_UNAVAILABLE")
        self.assertNotIn("internal connection detail", raised.exception.detail)

    @override_settings(ASSESSMENT_API_MAX_RESPONSE_BYTES=1024)
    @patch("integrations.ai.transport.requests.post")
    def test_oversized_response_is_rejected(self, post):
        response = Mock(status_code=200, headers={"Content-Type": "application/json"})
        response.iter_content.return_value = [b"x" * 1025]
        post.return_value.__enter__.return_value = response

        with self.assertRaises(AssessmentServiceError) as raised:
            request_assessment("safe")

        self.assertEqual(raised.exception.code, "ASSESSMENT_RESPONSE_INVALID")

    @patch("integrations.ai.transport.requests.post")
    def test_invalid_responses_are_rejected(self, post):
        for payload in ({"task_id": "pending"}, {"error": "private detail"}, {},
                        {"choices": []}, {"choices": [None]},
                        {"choices": [{"message": {"content": " "}}]},
                        {"choices": [{"message": {"content": ["text"]}}]}, []):
            with self.subTest(payload=payload):
                response = Mock(status_code=200, headers={"Content-Type": "application/json"})
                response.iter_content.return_value = [json.dumps(payload).encode()]
                post.return_value.__enter__.return_value = response
                with self.assertRaises(AssessmentServiceError) as raised:
                    request_assessment("safe")
                self.assertEqual(raised.exception.code, "ASSESSMENT_RESPONSE_INVALID")
                self.assertNotIn("private detail", str(raised.exception))

    @patch("integrations.ai.transport.requests.post")
    def test_missing_credentials_and_model_fail_before_network(self, post):
        for setting in ("ASSESSMENT_API_TOKEN", "ASSESSMENT_API_MODEL_ID"):
            with self.subTest(setting=setting), override_settings(**{setting: ""}):
                with self.assertRaises(AssessmentServiceError) as raised:
                    request_assessment("safe")
                self.assertEqual(raised.exception.code, "ASSESSMENT_CONFIGURATION_ERROR")
        post.assert_not_called()

    @patch("integrations.ai.transport.requests.post")
    def test_redirects_and_http_errors_are_rejected(self, post):
        for status in (302, 401, 500):
            response = Mock(status_code=status)
            post.return_value.__enter__.return_value = response
            with self.assertRaises(AssessmentServiceError) as raised:
                request_assessment("safe")
            self.assertEqual(raised.exception.code, "ASSESSMENT_UPSTREAM_REJECTED")
            response.iter_content.assert_not_called()

    @patch("integrations.ai.transport.requests.post")
    def test_invalid_encoding_json_and_content_type_are_rejected(self, post):
        for content_type, body in (("text/html", b"private"),
                                   ("text/event-stream", b"data: private"),
                                   ("application/json", b"not-json"),
                                   ("application/json", b"\xff")):
            response = Mock(status_code=200, headers={"Content-Type": content_type})
            response.iter_content.return_value = [body]
            post.return_value.__enter__.return_value = response
            with self.assertRaises(AssessmentServiceError) as raised:
                request_assessment("safe")
            self.assertEqual(raised.exception.code, "ASSESSMENT_RESPONSE_INVALID")

    @override_settings(
        AI_API_URL="https://central.internal.example/chat", AI_API_MODEL_ID="central-model",
        AI_API_TOKEN="central-test-only-token", AI_API_ALLOWED_HOSTS=["central.internal.example"],
    )
    @patch("integrations.ai.transport.requests.post")
    def test_assessment_delegates_to_central_client(self, post):
        response = Mock(status_code=200, headers={"Content-Type": "application/json"})
        response.iter_content.return_value = [b'{"choices":[{"message":{"content":"assessment"}}]}']
        post.return_value.__enter__.return_value = response
        prompt = "  Değerlendirme\noriginal prompt  "
        with patch("integrations.ai.client.complete_text", wraps=ai_client.complete_text) as complete:
            self.assertEqual(request_assessment(prompt), "assessment")
        complete.assert_called_once()
        messages = complete.call_args.args[0]
        self.assertEqual([(message.role, message.content) for message in messages], [("user", prompt)])
        configuration = complete.call_args.kwargs["configuration"]
        self.assertEqual(configuration.url, "https://assessment.internal.example/api/chat/completions")
        self.assertEqual(configuration.model, "test-model")
        self.assertEqual(configuration.token, "test-only-token")
        self.assertEqual(post.call_args.kwargs["json"], {
            "model": "test-model", "messages": [{"role": "user", "content": prompt}], "stream": False,
        })

    @patch("integrations.ai.transport.requests.post")
    def test_ai_error_maps_to_existing_assessment_error(self, post):
        response = Mock(status_code=200, headers={"Content-Type": "application/json"})
        response.iter_content.return_value = [b'{"choices":[{"message":{"content":"assessment"}}]}']
        post.return_value.__enter__.return_value = response
        for code, expected_code, detail, status in (
            ("AI_CONFIGURATION_ERROR", "ASSESSMENT_CONFIGURATION_ERROR", "The assessment service is not configured safely.", 503),
            ("AI_UNAVAILABLE", "ASSESSMENT_UNAVAILABLE", "The assessment service is unavailable.", 503),
            ("AI_UPSTREAM_REJECTED", "ASSESSMENT_UPSTREAM_REJECTED", "The assessment service rejected the request.", 502),
            ("AI_RESPONSE_INVALID", "ASSESSMENT_RESPONSE_INVALID", "The assessment service returned an invalid response.", 502),
            ("AI_INVALID_INPUT", "ASSESSMENT_INVALID_INPUT", "The assessment request is invalid.", 400),
        ):
            with self.subTest(code=code), patch(
                "integrations.ai.client.complete_text",
                side_effect=AIServiceError("private provider detail", code, status),
            ):
                with self.assertRaises(AssessmentServiceError) as raised:
                    request_assessment("safe")
                self.assertEqual((raised.exception.code, raised.exception.detail, raised.exception.response_status),
                                 (expected_code, detail, status))
                self.assertIsNone(raised.exception.__cause__)

    @patch("integrations.ai.transport.requests.post")
    def test_invalid_prompt_fails_safely_before_network(self, post):
        for prompt in (None, 42, [], "", " ", "\ud800"):
            with self.subTest(prompt=prompt):
                with self.assertRaises(AssessmentServiceError) as raised:
                    request_assessment(prompt)
                self.assertEqual(raised.exception.code, "ASSESSMENT_INVALID_INPUT")
                self.assertEqual(raised.exception.response_status, 400)
                self.assertEqual(raised.exception.detail, "The assessment request is invalid.")
        post.assert_not_called()

    @override_settings(
        ASSESSMENT_API_URL="", ASSESSMENT_API_MODEL_ID="", ASSESSMENT_API_TOKEN="",
        ASSESSMENT_API_ALLOWED_HOSTS=[], ASSESSMENT_API_CONNECT_TIMEOUT_SECONDS=5,
        ASSESSMENT_API_READ_TIMEOUT_SECONDS=60, ASSESSMENT_API_MAX_RESPONSE_BYTES=1024 * 1024,
        AI_API_URL="https://central.internal.example/chat", AI_API_MODEL_ID="central-model",
        AI_API_TOKEN="central-test-only-token", AI_API_ALLOWED_HOSTS=["central.internal.example"],
        AI_API_CONNECT_TIMEOUT_SECONDS=7, AI_API_READ_TIMEOUT_SECONDS=80,
        AI_API_MAX_RESPONSE_BYTES=8192,
    )
    @patch("integrations.ai.transport.requests.post")
    def test_assessment_uses_whole_central_family_when_legacy_absent(self, post):
        response = Mock(status_code=200, headers={"Content-Type": "application/json"})
        response.iter_content.return_value = [b'{"choices":[{"message":{"content":"assessment"}}]}']
        post.return_value.__enter__.return_value = response
        self.assertEqual(request_assessment("safe"), "assessment")
        self.assertEqual(post.call_args.args, ("https://central.internal.example/chat",))
        self.assertEqual(post.call_args.kwargs["timeout"], (7.0, 80.0))
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer central-test-only-token")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "central-model")

    @patch("integrations.ai.transport.requests.post")
    def test_large_document_prompt_remains_supported(self, post):
        response = Mock(status_code=200, headers={"Content-Type": "application/json"})
        response.iter_content.return_value = [b'{"choices":[{"message":{"content":"assessment"}}]}']
        post.return_value.__enter__.return_value = response
        prompt = "Belge görüşü: " * 100000
        self.assertEqual(request_assessment(prompt), "assessment")
        self.assertEqual(post.call_args.kwargs["json"]["messages"][0]["content"], prompt)

    @patch("integrations.ai.transport.requests.post")
    def test_oversized_document_prompt_fails_before_network(self, post):
        with self.assertRaises(AssessmentServiceError) as raised:
            request_assessment("x" * (16 * 1024 * 1024))
        self.assertEqual(raised.exception.code, "ASSESSMENT_INVALID_INPUT")
        self.assertEqual(raised.exception.response_status, 400)
        post.assert_not_called()
