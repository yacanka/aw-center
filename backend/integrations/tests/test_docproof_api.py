"""Regression tests for the DocProof integration helpers."""

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from requests.exceptions import RequestException, Timeout

from integrations import docproof_views as views
from integrations.docproof import base_url, login


class DocProofHelperTests(SimpleTestCase):
    """Verify DocProof parsing helpers preserve the public response behavior."""

    def test_find_latest_edms_object_id_uses_highest_pr_number(self):
        entries = [
            {"content": {"properties": {"pr_status": "DRAFT", "pr_no": 9, "id": "draft"}}},
            {"content": {"properties": {"pr_status": "EDMS", "pr_no": 1, "id": "old"}}},
            {"content": {"properties": {"pr_status": "EDMS", "pr_no": 3, "id": "new"}}},
        ]

        self.assertEqual(views.find_latest_edms_object_id(entries), "new")

    def test_find_document_issue_supports_existing_docproof_types(self):
        entries = [
            {"content": {"type": "ignored", "properties": {"issue": 1}}},
            {"content": {"type": "dprf_cdcp_document", "properties": {"issue": 7}}},
        ]

        self.assertEqual(views.find_document_issue(entries), 7)

    @override_settings(DOCPROOF_USERNAME="", DOCPROOF_PASSWORD="")
    def test_login_returns_false_without_credentials(self):
        self.assertFalse(login(Mock()))


class DocProofSearchTests(SimpleTestCase):
    """Verify the search flow without calling the external DocProof service."""

    @override_settings(DOCPROOF_URL="https://docproof.example.test")
    def test_search_issue_number_uses_params_and_timeout(self):
        client = self.build_client([
            {"total": 1, "entries": self.search_entries()},
            {"entries": self.document_entries(5)},
        ])

        self.assertEqual(views.search_issue_number("ABC-123", client), (5, None))
        client.get.assert_any_call(
            f"{views.base_url()}/realtime-queries/dprf_search_proof_readin",
            params={"inline": "true", "input_document_number": "ABC-123"},
            timeout=views.REQUEST_TIMEOUT_SECONDS,
            stream=True,
            allow_redirects=False,
        )

    @override_settings(DEBUG=False, DOCPROOF_URL="https://user:secret@docproof.example.test")
    def test_base_url_rejects_embedded_credentials(self):
        with self.assertRaises(RequestException):
            base_url()

    @override_settings(DOCPROOF_MAX_RESPONSE_BYTES=4)
    def test_response_size_is_bounded_even_without_content_length(self):
        response = Mock()
        response.headers = {}
        response.iter_content.return_value = [b"12345"]

        with self.assertRaises(RequestException):
            views.search_issue_number("ABC-123", self.build_http_client(response))

    def test_search_response_retries_once_after_http_error(self):
        with patch("integrations.docproof_views.search_document_issue", return_value=(4, None)):
            response = views.search_response("ABC-123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, 4)

    def test_search_response_sanitizes_upstream_failures(self):
        with patch(
            "integrations.docproof_views.search_document_issue",
            side_effect=Timeout("https://secret.internal/path"),
        ):
            response = views.search_response("ABC-123")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "DOCPROOF_UNAVAILABLE")
        self.assertNotIn("secret.internal", response.data["detail"])

    def test_search_response_keeps_missing_document_status(self):
        with patch("integrations.docproof_views.search_document_issue", return_value=(None, "missing")):
            response = views.search_response("UNKNOWN")

        self.assertEqual(response.status_code, 400)
        self.assertIn("UNKNOWN", response.data["message"])

    def test_search_response_keeps_unpublished_document_message(self):
        with patch("integrations.docproof_views.search_document_issue", return_value=(None, "unpublished")):
            response = views.search_response("DRAFT")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["message"], "Can not find published document in EDMS: DRAFT")

    def build_client(self, payloads):
        client = Mock()
        responses = []
        for payload in payloads:
            response = Mock()
            response.headers = {}
            response.iter_content.return_value = [
                __import__("json").dumps(payload).encode("utf-8")
            ]
            responses.append(response)
        client.get.side_effect = responses
        return client

    @staticmethod
    def build_http_client(response):
        client = Mock()
        client.get.return_value = response
        return client

    def search_entries(self):
        return [{"content": {"properties": {"pr_status": "EDMS", "pr_no": 1, "id": "42"}}}]

    def document_entries(self, issue):
        return [{"content": {"type": "dprf_technical_document", "properties": {"issue": issue}}}]
