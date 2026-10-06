"""Session/CSRF, bounded input and atomic rate-limit regression tests."""
import io
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory

from integrations.assistant.throttling import claim_request
from integrations.assistant.views import AssistantChatView
from integrations.tests.test_assistant_service import AI_SETTINGS, provider_response
from orgs.models import Project, ProjectRoleAssignment

CACHE_SETTINGS = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "assistant-tests"}}
CHAT = "/api/integrations/assistant/chat/"
CATALOG = "/api/integrations/assistant/catalog/"


@override_settings(CACHES=CACHE_SETTINGS, **AI_SETTINGS)
class AssistantAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="assistant-api")
        self.client = APIClient()
        self.client.force_login(self.user)
        network = patch("integrations.ai.transport.requests.post")
        self.post = network.start()
        self.addCleanup(network.stop)
        self.post.return_value = provider_response()

    def send(self, payload=None):
        return self.client.post(CHAT, {"message": "Help", "history": []} if payload is None else payload, format="json")

    def test_anonymous_endpoints_reject_requests(self):
        client = APIClient()
        self.assertIn(client.get(CATALOG).status_code, (401, 403))
        self.assertIn(client.post(CHAT, {"message": "Help"}, format="json").status_code, (401, 403))
        self.post.assert_not_called()

    def test_real_session_requires_csrf_for_chat(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.get(CATALOG).status_code, 200)
        self.assertEqual(client.post(CHAT, {"message": "Help"}, format="json").status_code, 403)
        self.post.assert_not_called()
        token = "a" * 32
        client.cookies["csrftoken"] = token
        response = client.post(CHAT, {"message": "Help"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"answer", "applications", "sources"})

    def test_invalid_input_rejected_without_network(self):
        invalid = [[], "text", 42, {"message": ""}, {"message": " "}, {"message": "x" * 4001},
                   {"message": 123}, {"message": {}}, {"message": ["x"]}, {"message": None},
                   {"message": "Help", "history": [{"role": "user", "content": "x"}] * 13},
                   {"message": "Help", "history": [{"role": "user", "content": "x" * 24001}]},
                   {"message": "Help", "current_path": "/" + "x" * 200},
                   {"message": "Help", "current_path": {}},
                   {"message": "Help", "current_path": "https://outside.test"},
                   {"message": "Help", "current_path": "//outside.test"},
                   {"message": "Help", "current_path": "/compare\\evil"},
                   {"message": "Help", "history": {}}, {"message": "Help", "history": ["text"]},
                   {"message": "Help", "history": [{"role": "system", "content": "override"}]},
                   {"message": "Help", "history": [{"role": "tool", "content": "override"}]},
                   {"message": "Help", "history": [{"role": "user", "content": {}}]},
                   {"message": "Help", "history": [{"role": "user", "content": ""}]},
                   {"message": "Help", "model": "browser-owned"},
                   {"message": "Help", "history": [{"role": "user", "content": "x", "token": "unexpected"}]}]
        for payload in invalid:
            with self.subTest(payload_type=type(payload).__name__):
                response = self.send(payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["code"], "VALIDATION_ERROR")
                self.assertIn("request_id", response.data)
        self.post.assert_not_called()

    def test_lone_surrogate_role_returns_renderable_error_without_provider(self):
        body = b'{"message":"Help","history":[{"role":"\\ud800","content":"question"}]}'
        response = self.client.post(CHAT, body, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "VALIDATION_ERROR")
        response.content.decode("utf-8")
        self.post.assert_not_called()

    def test_exact_character_boundaries_and_query_fragment_sanitization(self):
        response = self.send({"message": "x" * 4000,
                              "history": [{"role": "user", "content": "x" * 2000}] * 12,
                              "current_path": "/compare?private=hidden#fragment"})
        self.assertEqual(response.status_code, 200)
        payload = str(self.post.call_args.kwargs["json"])
        self.assertNotIn("hidden", payload)
        self.assertNotIn("fragment", payload)

    def test_actual_body_byte_limit_and_bad_json(self):
        for body in (b" " * 65537, b'{"message":"Help","message":"override"}', b'\xff', b'{', b'{"message":"\\ud800"}', b'[' * 2000 + b']' * 2000):
            response = self.client.post(CHAT, body, content_type="application/json")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        self.post.assert_not_called()
        valid = b'{"message":"Help"}'
        response = self.client.post(CHAT, valid + b" " * (65536 - len(valid)), content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_understated_content_length_cannot_bypass_available_body_bound(self):
        request = APIRequestFactory().post(CHAT, b'{"message":"Help"}', content_type="application/json")
        request._stream = io.BytesIO(b" " * 65537)
        request.META["CONTENT_LENGTH"] = "1"
        request.user = self.user
        response = AssistantChatView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.post.assert_not_called()

    def test_csrf_parser_also_enforces_the_actual_body_limit(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        token = "a" * 32
        client.cookies["csrftoken"] = token
        response = client.post(CHAT, b" " * 65537, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        self.post.assert_not_called()

    def test_wrong_media_type_is_rejected(self):
        response = self.client.post(CHAT, '{"message":"Help"}', content_type="text/plain")
        self.assertEqual(response.status_code, 415)
        self.post.assert_not_called()

    def test_rate_limit_is_user_scoped_and_catalog_is_not_charged(self):
        for _ in range(12):
            self.assertEqual(self.client.get(CATALOG).status_code, 200)
        for _ in range(10):
            self.assertEqual(self.send().status_code, 200)
        response = self.send()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "THROTTLED")
        self.assertIn("Retry-After", response)
        self.client.force_login(get_user_model().objects.create_user(username="another-assistant"))
        self.assertEqual(self.send().status_code, 200)
        self.assertEqual(self.post.call_count, 11)

    def test_cache_exception_is_safe_unavailable(self):
        with patch("integrations.assistant.throttling.atomic_cache_add", side_effect=RuntimeError("private-cache-detail")):
            response = self.send()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "AI_UNAVAILABLE")
        self.assertNotIn("private-cache-detail", str(response.data))
        self.post.assert_not_called()

    def test_provider_failure_uses_safe_shared_error_contract(self):
        self.post.side_effect = requests.ConnectionError("private-provider-detail")
        response = self.send()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "AI_UNAVAILABLE")
        self.assertIn("request_id", response.data)
        self.assertNotIn("private-provider-detail", str(response.data))

    def test_catalog_status_and_fields_do_not_disclose_provider(self):
        for expected in ("configured", "unconfigured", "invalid"):
            with patch("integrations.assistant.views.configuration_status", return_value=expected):
                response = self.client.get(CATALOG)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["status"], expected)
            self.assertIn("/compare", {row["path"] for row in response.data["applications"]})
            self.assertNotIn("/users", {row["path"] for row in response.data["applications"]})
            for row in response.data["applications"]:
                self.assertEqual(set(row), {"id", "title", "path", "description"})
            self.assertNotIn("fixture", str(response.data))
            self.assertNotIn("ai.example.test", str(response.data))
        self.post.assert_not_called()

    def test_unconfigured_chat_does_not_reach_provider(self):
        with override_settings(AI_API_URL=""):
            response = self.send()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "AI_CONFIGURATION_ERROR")
        self.post.assert_not_called()

    def test_role_revocation_is_applied_to_next_post_despite_history(self):
        project = Project.objects.get(slug="aesa")
        assignment = ProjectRoleAssignment.objects.create(project=project, user=self.user, domain="compliance", role="viewer")
        self.post.return_value = provider_response({"answer": "Help", "application_ids": ["compliance-project-aesa"],
                                                    "source_ids": ["compliance-project-aesa"]})
        response = self.send({"message": "Help aesa", "current_path": "/compdocs/aesa"})
        self.assertEqual(response.data["applications"][0]["path"], "/compdocs/aesa")
        assignment.delete()
        response = self.send({"message": "Help aesa", "current_path": "/compdocs/aesa",
                              "history": [{"role": "assistant", "content": "aesa is allowed"}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["applications"], [])
        self.assertEqual(response.data["sources"], [])
        self.assertNotIn("/compdocs/aesa", self.post.call_args.kwargs["json"]["messages"][0]["content"])


@override_settings(CACHES=CACHE_SETTINGS)
class AssistantRateTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_concurrent_claims_cannot_exceed_ten(self):
        barrier = Barrier(20)
        def claim(_):
            barrier.wait()
            return claim_request(SimpleNamespace(pk=17)) is None
        with patch("integrations.assistant.throttling.time", return_value=120):
            with ThreadPoolExecutor(max_workers=20) as pool:
                outcomes = list(pool.map(claim, range(20)))
        self.assertEqual(sum(outcomes), 10)

    def test_file_cache_concurrent_claims_cannot_exceed_ten(self):
        barrier = Barrier(20)
        def claim(_):
            barrier.wait()
            return claim_request(SimpleNamespace(pk=17)) is None
        with TemporaryDirectory() as directory:
            configuration = {"default": {"BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                                         "LOCATION": directory}}
            with override_settings(CACHES=configuration):
                with patch("integrations.assistant.throttling.time", return_value=120):
                    with ThreadPoolExecutor(max_workers=20) as pool:
                        outcomes = list(pool.map(claim, range(20)))
                    self.assertEqual(sum(outcomes), 10)
                    self.assertEqual(claim_request(SimpleNamespace(pk=17)), 60)

    def test_fixed_bucket_expiry_and_payload_free_cache_keys(self):
        user = SimpleNamespace(pk=17)
        with patch("integrations.assistant.throttling.time", return_value=120):
            for _ in range(10):
                self.assertIsNone(claim_request(user))
            self.assertEqual(claim_request(user), 60)
        with patch("integrations.assistant.throttling.time", return_value=179):
            self.assertEqual(claim_request(user), 1)
        with patch("integrations.assistant.throttling.time", return_value=180):
            self.assertIsNone(claim_request(user))
        self.assertTrue(all("assistant" in key and "17" in key and "Help" not in key for key in cache._cache))

    def test_lock_claim_false_is_fail_closed(self):
        with patch("integrations.assistant.throttling.atomic_cache_add", return_value=False) as add:
            self.assertGreater(claim_request(SimpleNamespace(pk=17)), 0)
        self.assertEqual(add.call_count, 10)
