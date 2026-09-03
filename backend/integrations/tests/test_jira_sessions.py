from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from orgs.models import Project, ProjectRoleAssignment

from integrations.jira.sessions import (
    JiraSessionConfigurationError,
    clear_jira_session,
    connect_jira_session,
    get_jira_session,
    owner_cache_key,
    session_cipher,
)
from integrations.jira.client import validated_session_id

TEST_FERNET_KEY = Fernet.generate_key().decode("ascii")
SESSION_URL = "/api/integrations/jira/session/"


@override_settings(
    DEBUG=True,
    JIRA_ENABLED=True,
    JIRA_URL="https://jira.example.test",
    JIRA_SESSION_ENCRYPTION_KEY=TEST_FERNET_KEY,
    JIRA_SESSION_TTL_SECONDS=60,
)
class JiraSessionTests(TestCase):
    """Protect the encrypted, owner-scoped JIRA session contract."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user("jira-owner", password="pass")
        self.other_user = get_user_model().objects.create_user("jira-other", password="pass")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        cache.clear()

    def test_validated_session_id_returns_the_normalized_credential(self):
        self.assertEqual(
            validated_session_id("  opaque-session-value  "),
            "opaque-session-value",
        )

    @patch("integrations.jira.sessions.JiraConnector")
    def test_post_encrypts_credential_and_returns_only_state_and_expiry(self, connector):
        connector.return_value.current_user.return_value = {
            "name": "jira-user",
            "displayName": "JIRA User",
            "emailAddress": "private@example.test",
        }
        credential = "opaque-session-credential"

        response = self.client.post(
            SESSION_URL,
            {"JSESSIONID": credential},
            format="json",
        )

        cached = cache.get(owner_cache_key(self.user))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "connected")
        self.assertEqual(set(response.data), {"state", "expires_at"})
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Pragma"], "no-cache")
        self.assertNotIn(credential, str(response.data))
        self.assertNotIn(credential, cached)
        decrypted = Fernet(TEST_FERNET_KEY.encode("ascii")).decrypt(cached.encode("ascii"))
        self.assertIn(credential.encode("utf-8"), decrypted)

    @patch("integrations.jira.sessions.JiraConnector")
    def test_session_is_owner_scoped_and_delete_is_idempotent(self, connector):
        connector.return_value.current_user.return_value = {
            "name": "jira-owner",
            "displayName": "Owner",
        }
        connect_jira_session(self.user, "owner-session-value")

        self.client.force_authenticate(self.other_user)
        other_response = self.client.get(SESSION_URL)
        self.client.force_authenticate(self.user)
        owner_response = self.client.get(SESSION_URL)
        first_delete = self.client.delete(SESSION_URL)
        second_delete = self.client.delete(SESSION_URL)

        self.assertEqual(other_response.data["state"], "disconnected")
        self.assertEqual(owner_response.data["state"], "connected")
        self.assertEqual(other_response["Cache-Control"], "no-store")
        self.assertEqual(owner_response["Cache-Control"], "no-store")
        self.assertEqual(first_delete.status_code, 204)
        self.assertEqual(first_delete["Cache-Control"], "no-store")
        self.assertEqual(second_delete.status_code, 204)
        self.assertIsNone(get_jira_session(self.user))

    @override_settings(JIRA_SESSION_TTL_SECONDS=1)
    @patch("integrations.jira.sessions.cache.set", wraps=cache.set)
    @patch("integrations.jira.sessions.JiraConnector")
    def test_reconnect_replaces_credential_and_refreshes_configured_ttl(
        self,
        connector,
        cache_set,
    ):
        connector.return_value.current_user.side_effect = [
            {"name": "first", "displayName": "First"},
            {"name": "second", "displayName": "Second"},
        ]

        first = connect_jira_session(self.user, "first-session-value")
        second = connect_jira_session(self.user, "second-session-value")
        resolved = get_jira_session(self.user)

        self.assertGreaterEqual(second.expires_at, first.expires_at)
        self.assertEqual(resolved.credential, "second-session-value")
        self.assertEqual(resolved.identity["username"], "second")
        self.assertEqual(cache_set.call_count, 2)
        self.assertEqual(cache_set.call_args.kwargs["timeout"], 1)

    @patch("integrations.jira.sessions.JiraConnector")
    def test_upstream_error_is_sanitized(self, connector):
        connector.return_value.current_user.side_effect = RuntimeError(
            "private upstream host and credential detail"
        )

        response = self.client.post(
            SESSION_URL,
            {"JSESSIONID": "opaque-session-value"},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "JIRA_SESSION_UNAVAILABLE")
        self.assertNotIn("private upstream", str(response.data))
        self.assertIsNone(cache.get(owner_cache_key(self.user)))

    @patch("integrations.jira.sessions.JiraConnector")
    def test_query_credentials_are_rejected_and_legacy_route_is_absent(self, connector):
        query_response = self.client.get(
            SESSION_URL,
            {"JSESSIONID": "query-session-secret"},
        )
        legacy_response = self.client.post(
            "/api/dcc/check_session/",
            {"JSESSIONID": "legacy-session-secret"},
            format="json",
        )

        self.assertEqual(query_response.status_code, 400)
        self.assertEqual(query_response.data["code"], "JIRA_SESSION_QUERY_FORBIDDEN")
        self.assertNotIn("query-session-secret", str(query_response.data))
        self.assertEqual(legacy_response.status_code, 404)
        connector.assert_not_called()

    @override_settings(DEBUG=False, JIRA_SESSION_ENCRYPTION_KEY="")
    def test_production_never_derives_an_encryption_key(self):
        with self.assertRaises(JiraSessionConfigurationError):
            session_cipher()

    def test_logout_service_clears_only_requested_owner(self):
        with patch("integrations.jira.sessions.JiraConnector") as connector:
            connector.return_value.current_user.return_value = {
                "name": "jira-owner",
                "displayName": "Owner",
            }
            connect_jira_session(self.user, "owner-session-value")
            connect_jira_session(self.other_user, "other-session-value")

        clear_jira_session(self.user)

        self.assertIsNone(get_jira_session(self.user))
        self.assertIsNotNone(get_jira_session(self.other_user))

    @patch("dcc.job_views.prepare_dcc_preview")
    @patch("dcc.job_views.capture_dcc_snapshot")
    @patch("dcc.job_views.jira_connector_for")
    def test_dcc_resolves_server_session_and_rejects_legacy_payload(
        self,
        connector_for,
        capture_snapshot,
        prepare_preview,
    ):
        project = Project.objects.get(slug="hys")
        ProjectRoleAssignment.objects.create(
            user=self.user,
            project=project,
            domain=ProjectRoleAssignment.Domain.DCC,
            role=ProjectRoleAssignment.Role.OPERATOR,
        )
        capture_snapshot.return_value = {
            "schema_version": 1,
            "issue_key": "CHN-42",
            "project_slug": "hys",
            "project_slugs": ["hys"],
            "project_ids": [project.pk],
            "project_label": "HYS",
            "output_name": "CHN-42.docx",
            "panel_count": 0,
            "placeholders": {},
        }
        prepare_preview.return_value = {
            "type": "dcc_preview",
            "issue_key": "CHN-42",
            "project": "HYS",
            "output_name": "CHN-42.docx",
            "panel_count": 0,
            "template_ready": True,
            "warning_count": 0,
        }

        response = self.client.post(
            "/api/dcc/jobs/create-document/preview/",
            {"url": "CHN-42"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="jira-session-preview-1",
        )
        legacy = self.client.post(
            "/api/dcc/jobs/create-document/preview/",
            {"url": "CHN-42", "JSESSIONID": "legacy-session-value"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="jira-session-preview-2",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(legacy.status_code, 400)
        self.assertEqual(legacy.data["code"], "JIRA_SESSION_CANONICAL_REQUIRED")
        connector_for.assert_called_once()
        self.assertEqual(connector_for.call_args.args[0].pk, self.user.pk)
