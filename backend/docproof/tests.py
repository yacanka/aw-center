"""Regression tests for the DocProof integration helpers."""

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from requests.exceptions import HTTPError

from docproof import views


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

    @override_settings(AW_USERNAME="", AW_PASSWORD="")
    def test_login_returns_false_without_credentials(self):
        self.assertFalse(views.login(Mock()))


class DocProofSearchTests(SimpleTestCase):
    """Verify the search flow without calling the external DocProof service."""

    def test_search_issue_number_uses_params_and_timeout(self):
        client = self.build_client([
            {"total": 1, "entries": self.search_entries()},
            {"entries": self.document_entries(5)},
        ])

        self.assertEqual(views.search_issue_number("ABC-123", client), (5, None))
        client.get.assert_any_call(
            f"{views.DOCPROOF_URL}/realtime-queries/dprf_search_proof_readin",
            params={"inline": "true", "input_document_number": "ABC-123"},
            timeout=views.REQUEST_TIMEOUT_SECONDS,
        )

    def test_search_response_retries_once_after_http_error(self):
        with patch("docproof.views.search_issue_number", side_effect=[HTTPError("expired"), (4, None)]):
            with patch("docproof.views.login") as login:
                response = views.search_response("ABC-123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, 4)
        login.assert_called_once()

    def test_search_response_keeps_missing_document_status(self):
        with patch("docproof.views.search_issue_number", return_value=(None, "missing")):
            response = views.search_response("UNKNOWN")

        self.assertEqual(response.status_code, 400)
        self.assertIn("UNKNOWN", response.data["message"])

    def test_search_response_keeps_unpublished_document_message(self):
        with patch("docproof.views.search_issue_number", return_value=(None, "unpublished")):
            response = views.search_response("DRAFT")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["message"], "Can not find published document in EDMS: DRAFT")

    def build_client(self, payloads):
        client = Mock()
        responses = []
        for payload in payloads:
            response = Mock()
            response.json.return_value = payload
            responses.append(response)
        client.get.side_effect = responses
        return client

    def search_entries(self):
        return [{"content": {"properties": {"pr_status": "EDMS", "pr_no": 1, "id": "42"}}}]

    def document_entries(self, issue):
        return [{"content": {"type": "dprf_technical_document", "properties": {"issue": issue}}}]
