"""Contracts for isolated, bounded AI calls; only the external HTTP boundary is mocked."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from integrations.ai import (
    AIConfiguration,
    AIRequestPolicy,
    AIServiceError,
    ChatMessage,
    complete_json,
    complete_text,
)


class AIClientTests(SimpleTestCase):
    def setUp(self):
        self.configuration = AIConfiguration(
            url="https://ai.internal.example/api/chat/completions",
            model="test-model",
            token="test-only-secret",
            allowed_hosts=("ai.internal.example",),
            connect_timeout=3,
            read_timeout=20,
            max_response_bytes=4096,
        )
        self.policy = AIRequestPolicy(
            purpose="test", max_request_bytes=4096, max_response_bytes=2048,
            connect_timeout=2, read_timeout=30,
        )
        self.messages = [ChatMessage("system", "safe system"), ChatMessage("user", "safe")]

    def response(self, content="answer", *, body=None, content_type="application/json", status=200):
        response = Mock(status_code=status, headers={"Content-Type": content_type})
        if body is None:
            body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        response.iter_content.return_value = [body]
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def call(self, messages=None, *, policy=None, configuration=None):
        return complete_text(
            self.messages if messages is None else messages,
            policy=self.policy if policy is None else policy,
            configuration=self.configuration if configuration is None else configuration,
        )

    @patch("integrations.ai.transport.requests.post")
    def test_text_request_is_bounded(self, post):
        context = self.response("first\nsecond")
        post.return_value = context
        self.assertEqual(self.call(), "first\nsecond")
        post.assert_called_once_with(
            self.configuration.url,
            json={"model": "test-model", "messages": [
                {"role": "system", "content": "safe system"},
                {"role": "user", "content": "safe"},
            ], "stream": False},
            headers={"Accept": "application/json", "Content-Type": "application/json; charset=utf-8",
                     "Authorization": "Bearer test-only-secret"},
            timeout=(2.0, 20.0), stream=True, allow_redirects=False,
        )
        context.__exit__.assert_called_once()

    @patch("integrations.ai.transport.requests.post")
    def test_utf8_limit_applies_to_encoded_payload(self, post):
        post.return_value = self.response()
        messages = [ChatMessage("user", "ğ🙂")]
        # requests' default JSON escaping encodes these as six and twelve ASCII bytes.
        payload = {"model": "test-model", "messages": [{"role": "user", "content": "ğ🙂"}], "stream": False}
        actual_bytes = len(requests.Request("POST", self.configuration.url, json=payload).prepare().body)
        self.assertEqual(actual_bytes, 105)
        self.call(messages, policy=replace(self.policy, max_request_bytes=actual_bytes))
        post.reset_mock()
        with self.assertRaises(AIServiceError) as raised:
            self.call(messages, policy=replace(self.policy, max_request_bytes=actual_bytes - 1))
        self.assertEqual(raised.exception.code, "AI_INVALID_INPUT")
        self.assertEqual(post.call_count, 0)

    @patch("integrations.ai.transport.requests.post")
    def test_invalid_messages_fail_before_network(self, post):
        cases = [[], "text", [None], [ChatMessage("tool", "safe")],
                 [ChatMessage("user", None)], [ChatMessage("user", " ")],
                 [ChatMessage("user", "\ud800")], [{"role": "user", "content": "safe"}]]
        for messages in cases:
            with self.subTest(messages=messages), self.assertRaises(AIServiceError) as raised:
                self.call(messages)
            self.assertEqual(raised.exception.code, "AI_INVALID_INPUT")
        self.assertEqual(post.call_count, 0)

    @patch("integrations.ai.transport.requests.post")
    def test_invalid_configuration_fails_before_network(self, post):
        invalid = [
            {"url": "http://ai.internal.example/ask"},
            {"url": "https://other.example/ask"},
            {"url": "https://user:password@ai.internal.example/ask"},
            {"url": "https://ai.internal.example/ask?secret=value"},
            {"url": "https://ai.internal.example/ask#fragment"},
            {"url": "https://ai.internal.example:bad/ask"},
            {"url": "https://ai.internal.example:65536/ask"},
            {"url": "https://[broken/ask"},
            {"url": "https://ai.internal.example\n/ask"},
            {"url": None}, {"model": ""}, {"model": None}, {"token": ""},
            {"token": "private\r\nvalue"}, {"token": None}, {"allowed_hosts": ()},
            {"allowed_hosts": ("*.internal.example",)}, {"allowed_hosts": None},
            {"connect_timeout": float("nan")}, {"connect_timeout": float("inf")},
            {"read_timeout": float("-inf")}, {"connect_timeout": 61},
            {"read_timeout": 301}, {"read_timeout": 0}, {"read_timeout": "bad"},
            {"max_response_bytes": 0}, {"max_response_bytes": 10 * 1024 * 1024 + 1},
            {"max_response_bytes": 1024.5},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(AIServiceError) as raised:
                self.call(configuration=replace(self.configuration, **values))
            self.assertEqual(raised.exception.code, "AI_CONFIGURATION_ERROR")
            self.assertNotIn("private", str(raised.exception))
        self.assertEqual(post.call_count, 0)

    @patch("integrations.ai.transport.requests.post")
    def test_invalid_policy_fails_before_network(self, post):
        for values in ({"purpose": ""}, {"max_request_bytes": 0}, {"max_response_bytes": -1},
                       {"max_response_bytes": True}, {"connect_timeout": float("nan")},
                       {"read_timeout": float("inf")}, {"read_timeout": 0}):
            with self.subTest(values=values), self.assertRaises(AIServiceError) as raised:
                self.call(policy=replace(self.policy, **values))
            self.assertEqual(raised.exception.code, "AI_INVALID_INPUT")
        self.assertEqual(post.call_count, 0)

    @patch("integrations.ai.transport.requests.post")
    def test_non_ascii_header_credential_fails_before_network(self, post):
        with self.assertRaises(AIServiceError) as raised:
            self.call(configuration=replace(self.configuration, token="invalid-🙂"))
        self.assertEqual(raised.exception.code, "AI_CONFIGURATION_ERROR")
        self.assertEqual(post.call_count, 0)

    @patch("integrations.ai.transport.requests.post")
    def test_response_limit_uses_lower_configuration_or_policy_bound(self, post):
        for configuration, policy in (
            (self.configuration, replace(self.policy, max_response_bytes=128)),
            (replace(self.configuration, max_response_bytes=1024), replace(self.policy, max_response_bytes=2048)),
        ):
            limit = min(configuration.max_response_bytes, policy.max_response_bytes)
            post.return_value = self.response(body=b"x" * (limit + 1))
            with self.subTest(limit=limit), self.assertRaises(AIServiceError) as raised:
                self.call(configuration=configuration, policy=policy)
            self.assertEqual(raised.exception.code, "AI_RESPONSE_INVALID")
            post.return_value.__exit__.assert_called_once()

    @patch("integrations.ai.transport.requests.post")
    def test_json_requires_object(self, post):
        for content in ("[]", "null", "not-json", '{"a": 1, "a": 2}', '{"nested": {"a": 1, "a": 2}}',
                        '{"value": NaN}', '{"value": Infinity}', '{"value": 1e400}'):
            post.reset_mock()
            post.return_value = self.response(content)
            with self.subTest(content=content):
                with self.assertRaises(AIServiceError) as raised:
                    complete_json(self.messages, policy=self.policy, configuration=self.configuration)
                self.assertEqual(raised.exception.code, "AI_RESPONSE_INVALID")
                self.assertEqual(post.call_count, 1)
        post.return_value = self.response('{"answer": [1, "safe"]}')
        self.assertEqual(complete_json(self.messages, policy=self.policy, configuration=self.configuration),
                         {"answer": [1, "safe"]})

    @patch("integrations.ai.transport.requests.post")
    def test_invalid_upstream_responses_are_sanitized(self, post):
        invalid = [b"", b"not-json", b"\xff", b"[]", b'{}', b'{"choices": []}',
                   b'{"choices": [null]}', b'{"choices": [1]}', b'{"choices": [{"message": null}]}',
                   b'{"choices": [{"message": {"content": " "}}]}',
                   b'{"choices": [{"message": {"content": []}}]}',
                   b'{"choices": [{"message": {"content": "safe"}}], "error": "private upstream"}',
                   b'{"task_id": "private upstream"}',
                   b'{"choices": [], "choices": [{"message": {"content": "safe"}}]}']
        for body in invalid:
            post.return_value = self.response(body=body)
            with self.subTest(body=body), self.assertRaises(AIServiceError) as raised:
                self.call()
            self.assertEqual(raised.exception.code, "AI_RESPONSE_INVALID")
            self.assertNotIn("private upstream", repr(raised.exception))
            self.assertNotIn(self.configuration.token, repr(raised.exception))

    @patch("integrations.ai.transport.requests.post")
    def test_wrong_content_type_is_rejected(self, post):
        for content_type in ("text/html", "text/event-stream", ""):
            post.return_value = self.response(content_type=content_type)
            with self.subTest(content_type=content_type), self.assertRaises(AIServiceError) as raised:
                self.call()
            self.assertEqual(raised.exception.code, "AI_RESPONSE_INVALID")

    @patch("integrations.ai.transport.requests.post")
    def test_redirects_and_http_errors_are_rejected_without_reading_body(self, post):
        for status in (302, 401, 500):
            context = self.response(status=status, body=b"private upstream")
            post.return_value = context
            with self.subTest(status=status), self.assertRaises(AIServiceError) as raised:
                self.call()
            self.assertEqual(raised.exception.code, "AI_UPSTREAM_REJECTED")
            self.assertEqual(raised.exception.response_status, 502)
            context.__enter__.return_value.iter_content.assert_not_called()
            context.__exit__.assert_called_once()

    @patch("integrations.ai.transport.requests.post")
    def test_network_and_stream_failures_are_sanitized_without_retry(self, post):
        for error in (requests.Timeout("private upstream test-only-secret"),
                      requests.ConnectionError("private upstream test-only-secret")):
            post.reset_mock()
            post.side_effect = error
            with self.subTest(error=type(error)), self.assertRaises(AIServiceError) as raised:
                self.call()
            self.assertEqual(raised.exception.code, "AI_UNAVAILABLE")
            self.assertEqual(raised.exception.response_status, 503)
            self.assertNotIn("private upstream", str(raised.exception))
            self.assertEqual(post.call_count, 1)
        post.side_effect = None
        post.return_value = self.response()
        post.return_value.__enter__.return_value.iter_content.side_effect = requests.Timeout("private")
        with self.assertRaises(AIServiceError) as raised:
            self.call()
        self.assertEqual(raised.exception.code, "AI_UNAVAILABLE")
        post.return_value.__exit__.assert_called_once()

    def test_configuration_is_immutable_and_hides_token(self):
        self.assertNotIn(self.configuration.token, repr(self.configuration))
        with self.assertRaises(FrozenInstanceError):
            self.configuration.token = "replacement"
        with self.assertRaises(FrozenInstanceError):
            self.messages[0].content = "replacement"
        with self.assertRaises(FrozenInstanceError):
            self.policy.purpose = "replacement"

    @patch("integrations.ai.transport.requests.post")
    def test_concurrent_calls_keep_separate_messages_and_policies(self, post):
        barrier = Barrier(2)
        observed = {}

        def transport(url, **kwargs):
            barrier.wait(timeout=5)
            payload = kwargs["json"]
            content = payload["messages"][0]["content"]
            observed[content] = (url, payload, kwargs["timeout"])
            return self.response(content)

        post.side_effect = transport
        second_configuration = replace(self.configuration, model="other-model", connect_timeout=1)
        second_policy = replace(self.policy, purpose="other", read_timeout=4)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self.call, [ChatMessage("user", "first")])
            second = executor.submit(self.call, [ChatMessage("user", "second")],
                                     configuration=second_configuration, policy=second_policy)
            self.assertEqual(first.result(timeout=10), "first")
            self.assertEqual(second.result(timeout=10), "second")
        self.assertEqual(observed["first"][1], {"model": "test-model", "messages": [{"role": "user", "content": "first"}], "stream": False})
        self.assertEqual(observed["second"][1], {"model": "other-model", "messages": [{"role": "user", "content": "second"}], "stream": False})
        self.assertEqual(observed["first"][2], (2.0, 20.0))
        self.assertEqual(observed["second"][2], (1.0, 4.0))
