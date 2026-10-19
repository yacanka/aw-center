"""Authentication selection at the outbound Jira transport boundary."""

from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from integrations.jira.client import JiraConfigurationError, JiraConnector


@override_settings(DEBUG=False, JIRA_VERIFY_SSL=True, JIRA_CERTIFICATE_FILE=Path("/missing-ca.pem"))
class JiraAuthenticationTests(SimpleTestCase):
    @patch("integrations.jira.client.JIRA")
    def test_pat_uses_bearer_transport_without_a_session_cookie(self, jira):
        JiraConnector("https://jira.example.test", personal_access_token="fixture-token-value")
        self.assertEqual(jira.call_args.kwargs["token_auth"], "fixture-token-value")
        self.assertIs(jira.call_args.kwargs["options"]["verify"], True)
        self.assertEqual(jira.call_args.kwargs["timeout"], 10)
        jira.return_value._session.cookies.set.assert_not_called()

    @patch("integrations.jira.client.JIRA")
    def test_session_uses_only_a_scoped_cookie(self, jira):
        JiraConnector("https://jira.example.test/jira", "fixture-session-value")
        self.assertNotIn("token_auth", jira.call_args.kwargs)
        jira.return_value._session.cookies.set.assert_called_once_with(
            "JSESSIONID", "fixture-session-value", domain="jira.example.test", path="/jira",
        )

    @patch("integrations.jira.client.JIRA")
    def test_ambiguous_or_invalid_credentials_fail_before_transport_initialization(self, jira):
        for credentials in (
            {}, {"jira_session_id": "fixture-session", "personal_access_token": "fixture-token"},
            {"personal_access_token": "fixture\x00token"},
        ):
            with self.subTest(keys=list(credentials)), self.assertRaises(ValueError):
                JiraConnector("https://jira.example.test", **credentials)
        jira.assert_not_called()

    @override_settings(JIRA_VERIFY_SSL=False)
    @patch("integrations.jira.client.JIRA")
    def test_pat_cannot_disable_tls_verification_in_production(self, jira):
        with self.assertRaises(JiraConfigurationError):
            JiraConnector("https://jira.example.test", personal_access_token="fixture-token-value")
        jira.assert_not_called()
