import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from jira import JIRAError
from rest_framework.test import APIClient
from orgs.models import Project, ProjectRoleAssignment

from integrations.jira.sessions import (
    JiraSessionConfigurationError,
    JiraSessionNotConnected,
    clear_jira_session,
    connect_jira_session,
    ensure_jira_enabled,
    get_jira_session,
    jira_connector_for,
    owner_cache_key,
    require_jira_session,
    session_cipher,
    store_jira_session,
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

    def test_disabled_owner_cannot_reuse_a_cached_session_through_a_stale_user(self):
        store_jira_session(self.other_user, "other-session-fixture", {"username": "other"})
        for is_superuser in (False, True):
            for use_identifier in (False, True):
                with self.subTest(is_superuser=is_superuser, use_identifier=use_identifier):
                    get_user_model().objects.filter(pk=self.user.pk).update(
                        is_active=True, is_superuser=is_superuser,
                    )
                    self.user.refresh_from_db()
                    store_jira_session(self.user, "owner-session-fixture", {"username": "owner"})
                    owner = self.user.pk if use_identifier else self.user
                    self.assertIsNotNone(require_jira_session(owner))
                    get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)

                    with self.assertRaises(JiraSessionNotConnected):
                        require_jira_session(owner)

                    self.assertIsNone(cache.get(owner_cache_key(self.user)))
                    self.assertIsNotNone(require_jira_session(self.other_user))

    @patch("integrations.jira.sessions.JiraConnector")
    def test_post_encrypts_credential_and_returns_only_public_identity_and_state(self, connector):
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
        self.assertEqual(set(response.data), {"state", "expires_at", "user"})
        self.assertEqual(response.data["user"], {
            "username": "jira-user", "display_name": "JIRA User",
        })
        self.assertNotIn("emailAddress", str(response.data))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Pragma"], "no-cache")
        self.assertNotIn(credential, str(response.data))
        self.assertNotIn(credential, cached)
        decrypted = Fernet(TEST_FERNET_KEY.encode("ascii")).decrypt(cached.encode("ascii"))
        self.assertIn(credential.encode("utf-8"), decrypted)

    @patch("integrations.jira.sessions.JiraConnector")
    def test_pat_matches_owner_case_insensitively_and_is_reused_by_tools(self, connector):
        connector.return_value.current_user.return_value = {
            "name": "JIRA-OWNER", "displayName": "Owner", "emailAddress": "private@example.test",
        }
        response = self.client.post(
            SESSION_URL, {"personal_access_token": "fixture-personal-access-token"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"], {"username": "JIRA-OWNER", "display_name": "Owner"})
        self.assertNotIn("fixture-personal-access-token", str(response.data))
        self.assertNotIn("fixture-personal-access-token", cache.get(owner_cache_key(self.user)))
        record = get_jira_session(self.user)
        self.assertEqual(record.auth_method, "personal_access_token")
        self.assertEqual(record.credential, "fixture-personal-access-token")
        self.assertEqual(self.client.get(SESSION_URL).data, response.data)
        jira_connector_for(self.user)
        self.assertEqual(connector.call_args.kwargs, {
            "personal_access_token": "fixture-personal-access-token",
        })
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(SESSION_URL).data["state"], "disconnected")
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(SESSION_URL).status_code, 204)
        self.assertIsNone(get_jira_session(self.user))

    @patch("integrations.jira.sessions.JiraConnector")
    def test_pat_for_another_account_cannot_replace_an_existing_connection(self, connector):
        connector.return_value.current_user.return_value = {"name": "previous-jira-account"}
        connect_jira_session(self.user, "previous-session-fixture")
        connector.return_value.current_user.return_value = {"name": "another-jira-account"}
        response = self.client.post(
            SESSION_URL,
            {"personal_access_token": "fixture-personal-access-token", "username": "another-jira-account"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "JIRA_ACCOUNT_MISMATCH")
        self.assertNotIn("another-jira-account", str(response.data))
        self.assertEqual(get_jira_session(self.user).credential, "previous-session-fixture")

    @patch("integrations.jira.sessions.JiraConnector")
    def test_invalid_pat_and_upstream_failure_do_not_store_a_connection(self, connector):
        for status, expected_status in ((401, 400), (403, 400), (503, 502)):
            with self.subTest(status=status):
                connector.return_value.current_user.side_effect = JIRAError(
                    status_code=status, text="private upstream detail",
                )
                response = self.client.post(
                    SESSION_URL, {"personal_access_token": "fixture-token-value"}, format="json",
                )
                self.assertEqual(response.status_code, expected_status)
                self.assertNotIn("private upstream", str(response.data))
                self.assertEqual(response["Cache-Control"], "no-store")
                self.assertIsNone(get_jira_session(self.user))

    @patch("integrations.jira.sessions.JiraConnector")
    def test_connect_requires_exactly_one_safe_credential(self, connector):
        for payload in (
            {}, {"JSESSIONID": "fixture-session", "personal_access_token": "fixture-token"},
            {"personal_access_token": ""}, {"personal_access_token": "short"},
            {"personal_access_token": "token with space"},
            {"personal_access_token": "token\r\ninjected"},
            {"personal_access_token": "non-ascii-ş-token"},
            {"personal_access_token": "token\x00value"},
            {"personal_access_token": "x" * 4097},
        ):
            with self.subTest(payload_keys=list(payload)):
                response = self.client.post(SESSION_URL, payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response["Cache-Control"], "no-store")
        connector.assert_not_called()

    @patch("integrations.jira.sessions.JiraConnector")
    def test_old_cache_records_without_auth_method_remain_session_connections(self, connector):
        connector.return_value.current_user.return_value = {"name": "session-owner"}
        connect_jira_session(self.user, "fixture-session")
        cipher = session_cipher()
        payload = json.loads(cipher.decrypt(cache.get(owner_cache_key(self.user)).encode("ascii")))
        payload.pop("auth_method", None)
        cache.set(owner_cache_key(self.user), cipher.encrypt(json.dumps(payload).encode()).decode("ascii"))
        self.assertEqual(get_jira_session(self.user).auth_method, "session_id")
        jira_connector_for(self.user)
        self.assertEqual(connector.call_args.kwargs, {"jira_session_id": "fixture-session"})

    @patch("integrations.jira.sessions.JiraConnector")
    def test_pat_credentials_are_forbidden_in_query_and_business_payloads(self, connector):
        for method in (self.client.get, self.client.post, self.client.delete):
            response = method(SESSION_URL + "?personal_access_token=fixture-token")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["code"], "JIRA_SESSION_QUERY_FORBIDDEN")
            self.assertNotIn("fixture-token", str(response.data))
        from integrations.jira.sessions import has_legacy_jira_credential
        self.assertTrue(has_legacy_jira_credential({"nested": [{"personal_access_token": "fixture-token"}]}))
        connector.assert_not_called()

    @patch("integrations.jira.sessions.JiraConnector")
    def test_pat_expiry_and_invalid_cache_entries_are_cleared(self, connector):
        connector.return_value.current_user.return_value = {"name": "jira-owner"}
        connect_jira_session(self.user, "fixture-token", auth_method="personal_access_token")
        with patch("integrations.jira.sessions.timezone.now", return_value=timezone.now() + timedelta(seconds=61)):
            self.assertIsNone(get_jira_session(self.user))
        for payload in ([], {"auth_method": "unknown"}):
            cache.set(owner_cache_key(self.user), session_cipher().encrypt(json.dumps(payload).encode()).decode("ascii"))
            self.assertIsNone(get_jira_session(self.user))
            self.assertIsNone(cache.get(owner_cache_key(self.user)))

    @patch("integrations.jira.sessions.JiraConnector")
    def test_pat_connection_requires_browser_authentication_and_csrf(self, connector):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(SESSION_URL, {"personal_access_token": "fixture-token"}, format="json")
        self.assertEqual(response.status_code, 403)
        client.force_login(self.user)
        response = client.post(SESSION_URL, {"personal_access_token": "fixture-token"}, format="json")
        self.assertEqual(response.status_code, 403)
        connector.assert_not_called()

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
            "/api/integrations/jira/check_session/",
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

    @override_settings(DEBUG=True, JIRA_SESSION_ENCRYPTION_KEY="")
    def test_development_never_derives_an_encryption_key(self):
        with self.assertRaises(JiraSessionConfigurationError):
            session_cipher()

    @patch("integrations.jira.sessions.JiraConnector")
    def test_jira_key_is_independent_and_rotation_requires_reconnection(self, connector):
        connector.return_value.current_user.return_value = {"name": "jira-owner"}
        connect_jira_session(self.user, "synthetic-session-value")

        with override_settings(SECRET_KEY="synthetic-rotated-django-key"):
            self.assertEqual(get_jira_session(self.user).credential, "synthetic-session-value")

        with override_settings(JIRA_SESSION_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii")):
            self.assertIsNone(get_jira_session(self.user))
            self.assertIsNone(cache.get(owner_cache_key(self.user)))
            connect_jira_session(self.user, "synthetic-reconnected-value")
            self.assertEqual(get_jira_session(self.user).credential, "synthetic-reconnected-value")
            self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

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

    @patch("integrations.jira.job_views.prepare_dcc_preview")
    @patch("integrations.jira.job_views.capture_dcc_snapshot")
    @patch("integrations.jira.job_views.jira_connector_for")
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
            domain=ProjectRoleAssignment.Domain.JIRA,
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
            "/api/integrations/jira/jobs/create-document/preview/",
            {"url": "CHN-42"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="jira-session-preview-1",
        )
        legacy = self.client.post(
            "/api/integrations/jira/jobs/create-document/preview/",
            {"url": "CHN-42", "JSESSIONID": "legacy-session-value"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="jira-session-preview-2",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(legacy.status_code, 400)
        self.assertEqual(legacy.data["code"], "JIRA_SESSION_CANONICAL_REQUIRED")
        connector_for.assert_called_once()
        self.assertEqual(connector_for.call_args.args[0].pk, self.user.pk)

    @override_settings(DEBUG=False, AWCENTER_DEPLOYMENT_MODE="windows-native")
    @patch("integrations.jira.sessions.JiraConnector")
    def test_windows_file_cache_shares_encrypted_owner_session_with_another_process(
        self, connector
    ):
        connector.return_value.current_user.return_value = {"name": "jira-owner"}
        with TemporaryDirectory() as directory:
            config = {
                "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                "LOCATION": directory,
            }
            with override_settings(CACHES={"default": config}):
                response = self.client.post(
                    SESSION_URL, {"JSESSIONID": "process-session-fixture"}, format="json"
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("process-session-fixture", str(response.data))
                self.assertNotIn(
                    "process-session-fixture", cache.get(owner_cache_key(self.user))
                )
                self.assertIsNone(get_jira_session(self.other_user))
                child = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        """
import json, sys, django
from django.test import override_settings
config = json.load(sys.stdin)
django.setup()
from integrations.jira.sessions import ensure_jira_enabled, get_jira_session, clear_jira_session
with override_settings(DEBUG=False, AWCENTER_DEPLOYMENT_MODE="windows-native",
        JIRA_ENABLED=True, JIRA_SESSION_ENCRYPTION_KEY=config["key"],
        CACHES={"default": config["cache"]}):
    ensure_jira_enabled()
    record = get_jira_session(config["owner"])
    result = {"owned": record is not None and record.credential == "process-session-fixture",
              "other": get_jira_session(config["other"]) is None}
    clear_jira_session(config["owner"])
    print(json.dumps(result))
""",
                    ],
                    input=json.dumps({
                        "cache": config,
                        "key": TEST_FERNET_KEY,
                        "owner": self.user.pk,
                        "other": self.other_user.pk,
                    }),
                    text=True,
                    capture_output=True,
                    timeout=30,
                    cwd=Path(__file__).resolve().parents[2],
                )
                self.assertEqual(child.returncode, 0, child.stderr)
                self.assertEqual(json.loads(child.stdout), {"owned": True, "other": True})
                self.assertIsNone(get_jira_session(self.user))
                self.assertEqual(self.client.delete(SESSION_URL).status_code, 204)

    @override_settings(DEBUG=False, AWCENTER_DEPLOYMENT_MODE="windows-native")
    @patch("integrations.jira.sessions.JiraConnector")
    def test_windows_file_cache_discards_expired_and_corrupt_sessions(self, connector):
        connector.return_value.current_user.return_value = {"name": "jira-owner"}
        with TemporaryDirectory() as directory:
            with override_settings(
                CACHES={"default": {
                    "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                    "LOCATION": directory,
                }}
            ):
                connect_jira_session(self.user, "expiry-session-fixture")
                with patch(
                    "integrations.jira.sessions.timezone.now",
                    return_value=timezone.now() + timedelta(seconds=61),
                ):
                    self.assertIsNone(get_jira_session(self.user))
                self.assertIsNone(cache.get(owner_cache_key(self.user)))
                cache.set(owner_cache_key(self.user), "corrupt-ciphertext")
                self.assertIsNone(get_jira_session(self.user))
                self.assertIsNone(cache.get(owner_cache_key(self.user)))

    @override_settings(DEBUG=False)
    def test_production_rejects_cache_that_does_not_match_deployment_profile(self):
        file_backend = "django.core.cache.backends.filebased.FileBasedCache"
        redis_backend = "django.core.cache.backends.redis.RedisCache"
        cases = [
            ("windows-native", {"BACKEND": redis_backend}),
            ("windows-native", {"BACKEND": file_backend, "LOCATION": "relative-cache"}),
            ("windows-native", {
                "BACKEND": file_backend,
                "LOCATION": str(Path(__file__).resolve().parents[3] / "cache"),
            }),
            ("container", {"BACKEND": file_backend, "LOCATION": "/tmp/cache"}),
            ("development", {"BACKEND": redis_backend}),
        ]
        for mode, config in cases:
            with self.subTest(mode=mode, config=config):
                with override_settings(
                    AWCENTER_DEPLOYMENT_MODE=mode, CACHES={"default": config}
                ):
                    with self.assertRaises(JiraSessionConfigurationError):
                        ensure_jira_enabled()

    @override_settings(
        DEBUG=False,
        AWCENTER_DEPLOYMENT_MODE="container",
        CACHES={"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache"}},
    )
    def test_container_keeps_redis_session_policy(self):
        ensure_jira_enabled()
