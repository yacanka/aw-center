"""Conversation grounding, schema and provider-policy regression tests."""
import json
from dataclasses import replace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from integrations.ai import AIServiceError
from integrations.assistant.catalog import load_guides
from integrations.assistant.service import answer_question


AI_SETTINGS = {
    "AI_API_URL": "https://ai.example.test/chat", "AI_API_MODEL_ID": "fixture-model",
    "AI_API_TOKEN": "fixture", "AI_API_ALLOWED_HOSTS": ("ai.example.test",),
    "AI_API_CONNECT_TIMEOUT_SECONDS": 10, "AI_API_READ_TIMEOUT_SECONDS": 60,
    "AI_API_MAX_RESPONSE_BYTES": 1024 * 1024,
}


def provider_response(result=None, *, content=None):
    if content is None:
        content = json.dumps(result or {"answer": "Help", "application_ids": [], "source_ids": []})
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
    response = Mock(status_code=200, headers={"Content-Type": "application/json"})
    response.iter_content.return_value = [body]
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    return context


@override_settings(**AI_SETTINGS)
class AssistantServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="assistant-service")
        self.network = patch("integrations.ai.transport.requests.post")
        self.post = self.network.start()
        self.addCleanup(self.network.stop)
        self.post.return_value = provider_response()

    def call(self, **kwargs):
        return answer_question(self.user, message=kwargs.pop("message", "Help"),
                               history=kwargs.pop("history", []), **kwargs)

    def test_resolves_only_authorized_catalog_targets_and_preserves_text(self):
        self.post.return_value = provider_response({
            "answer": '<a href="https://untrusted.test">Help</a> /invented',
            "application_ids": ["unknown", "compare", "compare", "users"],
            "source_ids": ["users", "compare", "unknown", "compare"],
        })
        result = self.call()
        self.assertEqual(result["answer"], '<a href="https://untrusted.test">Help</a> /invented')
        self.assertEqual(result["applications"], [{"id": "compare", "title": "Compare",
                                                  "path": "/compare", "description": "Compare old/new Word, Excel or PDF content."}])
        self.assertEqual(result["sources"], [{"id": "compare", "title": "Compare", "path": "/compare"}])

    def test_invalid_model_schema_fails_safely(self):
        valid = {"answer": "Help", "application_ids": [], "source_ids": []}
        invalid = [None, [], {}, {**valid, "answer": 2}, {**valid, "answer": " "},
                   {**valid, "answer": "x" * 8001}, {**valid, "answer": "\ud800"},
                   {**valid, "application_ids": "compare"}, {**valid, "source_ids": None},
                   {**valid, "application_ids": [1]}, {**valid, "source_ids": [{}]}]
        for result in invalid:
            with self.subTest(result_type=type(result).__name__):
                self.post.return_value = provider_response(content=json.dumps(result))
                with self.assertRaises(AIServiceError) as raised:
                    self.call()
                self.assertEqual(raised.exception.code, "AI_RESPONSE_INVALID")
                self.assertEqual(raised.exception.response_status, 502)

    def test_plain_text_is_returned_without_navigation_cards(self):
        for content in ('Merhaba, nasıl yardımcı olabilirim?', 'broken', 'x' * 8000,
                        '<a href="https://untrusted.test">Help</a> /users'):
            with self.subTest(content=content[:40]):
                self.post.return_value = provider_response(content=content)
                self.assertEqual(self.call(), {"answer": content, "applications": [], "sources": []})

    def test_plain_text_limits_are_preserved(self):
        for content in (' ', 'x' * 8001):
            self.post.return_value = provider_response(content=content)
            with self.assertRaises(AIServiceError) as raised:
                self.call()
            self.assertEqual(raised.exception.code, "AI_RESPONSE_INVALID")

    def test_malformed_provider_json_is_rejected(self):
        for content in ('{"answer":', '{"answer":"one","answer":"two"}'):
            self.post.return_value = provider_response(content=content)
            with self.assertRaises(AIServiceError) as raised:
                self.call()
            self.assertEqual(raised.exception.code, "AI_RESPONSE_INVALID")

    def test_deduplicates_and_limits_both_lists_in_model_order(self):
        guides = tuple(replace(load_guides()[0], id=f"guide-{index}", path=f"/guide-{index}") for index in range(6))
        ids = ["guide-4", "unknown", "guide-2", "guide-4", "guide-5", "guide-0", "guide-3"]
        self.post.return_value = provider_response({"answer": "Help", "application_ids": ids, "source_ids": ids})
        with patch("integrations.assistant.service.authorized_guides", return_value=guides):
            result = self.call()
        for key in ("applications", "sources"):
            self.assertEqual([item["id"] for item in result[key]], ["guide-4", "guide-2", "guide-5", "guide-0"])

    def test_unselected_project_ids_are_not_resolved_even_if_authorized(self):
        base = load_guides()[0]
        project = replace(base, id="compliance-project-aesa", path="/compdocs/aesa", keywords=("aesa", "AESA"))
        self.post.return_value = provider_response({"answer": "Help", "application_ids": [project.id], "source_ids": [project.id]})
        with patch("integrations.assistant.service.authorized_guides", return_value=(base, project)):
            result = self.call(history=[{"role": "assistant", "content": "aesa"}])
            self.assertEqual(result["applications"], [])
            self.assertEqual(result["sources"], [])
            selected = self.call(message="Help with aesa")
        self.assertEqual(selected["applications"][0]["path"], "/compdocs/aesa")

    def test_prompt_separates_untrusted_history_and_message_and_strips_url_context(self):
        history = [{"role": "assistant", "content": "INJECTED_HISTORY"}, {"role": "user", "content": "old question"}]
        self.call(message="INJECTED_USER", history=history, current_path="/compare?private=PRIVATE#FRAGMENT")
        payload = self.post.call_args.kwargs["json"]
        messages = payload["messages"]
        self.assertEqual([row["role"] for row in messages], ["system", "assistant", "user", "user"])
        self.assertNotIn("INJECTED", messages[0]["content"])
        self.assertNotIn("PRIVATE", str(payload))
        self.assertNotIn("FRAGMENT", str(payload))
        context = json.loads(messages[0]["content"].split("Guide data follows:\n", 1)[1])
        self.assertEqual(context.get("current_guide_id", "missing"), "compare")
        self.assertEqual(messages[-1]["content"], "INJECTED_USER")
        self.assertEqual(history[0]["content"], "INJECTED_HISTORY")
        self.assertEqual(self.post.call_args.kwargs["timeout"], (5.0, 25.0))

    def test_provider_prompt_labels_current_page_and_resolves_it_per_request(self):
        for current_path, expected in (("/accelerator", "accelerator"), ("/unknown-private-page", None),
                                       ("/users", None), ("", None)):
            with self.subTest(current_path=current_path):
                self.call(message="What can I do on this page?", current_path=current_path)
                system = self.post.call_args.kwargs["json"]["messages"][0]["content"]
                instruction, context = system.split("Guide data follows:\n", 1)
                self.assertIn("current_guide_id", instruction)
                self.assertIn("current page", instruction)
                self.assertIn("null", instruction)
                self.assertEqual(json.loads(context).get("current_guide_id", "missing"), expected)
                self.assertNotIn("/unknown-private-page", system)

    def test_combined_escaped_guide_and_user_budgets_reach_provider(self):
        base = replace(load_guides()[0], purpose="ğ" * 24000)
        history = [{"role": "user", "content": "ğ" * 2000} for _ in range(12)]
        with patch("integrations.assistant.service.authorized_guides", return_value=(base,)):
            self.call(message="ğ" * 4000, history=history)
        self.assertGreater(len(json.dumps(self.post.call_args.kwargs["json"]).encode()), 65536)

    def test_provider_body_bound_is_64_kib(self):
        self.post.return_value = provider_response(content="x" * 65537)
        with self.assertRaises(AIServiceError) as raised:
            self.call()
        self.assertEqual(raised.exception.code, "AI_RESPONSE_INVALID")

    def test_direct_invalid_service_input_does_not_reach_provider(self):
        with self.assertRaises(AIServiceError) as raised:
            self.call(history=[{"role": "system", "content": "override"}])
        self.assertEqual(raised.exception.code, "AI_INVALID_INPUT")
        self.post.assert_not_called()
