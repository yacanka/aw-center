"""Focused tests for fail-closed production configuration checks."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .checks import _frontend_capability_url_checks, production_runtime_checks


class ProductionConfigurationCheckTests(SimpleTestCase):
    def error_ids(self):
        return {error.id for error in production_runtime_checks(None)}

    @override_settings(
        DEBUG=False,
        SECRET_KEY="replace-with-a-long-random-production-secret",
    )
    def test_template_secret_is_rejected(self):
        self.assertIn("awcenter.E003", self.error_ids())

    @override_settings(
        DEBUG=False,
        JIRA_ENABLED=True,
        JIRA_URL="https://jira.example.test",
        JIRA_SESSION_ENCRYPTION_KEY="not-a-fernet-key",
    )
    def test_jira_encryption_key_is_validated(self):
        self.assertIn("awcenter.E018", self.error_ids())

    @override_settings(
        DEBUG=False,
        DOCPROOF_ENABLED=True,
        DOCPROOF_URL="https://docproof.example.test",
        DOCPROOF_USERNAME="",
        DOCPROOF_PASSWORD="",
        DOCPROOF_VERIFY_SSL=False,
    )
    def test_docproof_credentials_and_tls_are_required(self):
        with TemporaryDirectory() as directory:
            with override_settings(
                DOCPROOF_CERTIFICATE_FILE=Path(directory) / "missing-ca.pem"
            ):
                identifiers = self.error_ids()
        self.assertIn("awcenter.E019", identifiers)
        self.assertIn("awcenter.E020", identifiers)

    @override_settings(
        DEBUG=False,
        TEAMCENTER_ENABLED=True,
        TEAMCENTER_BASE_URL="https://user:secret@teamcenter.example.test?unsafe=1",
    )
    def test_integration_urls_reject_credentials_and_request_parts(self):
        self.assertIn("awcenter.E012", self.error_ids())

    @override_settings(
        DEBUG=False,
        NUMARATOR_ENABLED=True,
        NUMARATOR_BASE_URL="http://numarator.example.test",
        NUMARATOR_CREDENTIAL_ID="",
        NUMARATOR_PROJECT_FORMATS={},
        NUMARATOR_VERIFY_SSL=False,
    )
    def test_numarator_requires_secure_complete_non_secret_configuration(self):
        identifiers = self.error_ids()
        self.assertTrue({"awcenter.E027", "awcenter.E028", "awcenter.E029"}.issubset(identifiers))

    @override_settings(
        DEBUG=False,
        ASSESSMENT_API_URL="https://assessment.example.test/api",
        ASSESSMENT_API_ALLOWED_HOSTS=[],
    )
    def test_assessment_host_requires_explicit_allowlist(self):
        self.assertIn("awcenter.E023", self.error_ids())

    @override_settings(DEBUG=False, DOORS_ENABLED=True)
    def test_doors_requires_windows(self):
        with patch("awcenter.checks.sys.platform", "win32"):
            self.assertNotIn("awcenter.E034", self.error_ids())
        with patch("awcenter.checks.sys.platform", "linux"):
            self.assertIn("awcenter.E034", self.error_ids())

    @override_settings(
        DEBUG=False,
        AWCENTER_DEPLOYMENT_MODE="container",
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
        TRUST_PROXY_HEADERS=False,
        TRUSTED_PROXY_COUNT=0,
    )
    def test_future_container_mode_keeps_postgres_redis_and_proxy_contract(self):
        self.assertTrue(
            {"awcenter.E001", "awcenter.E002", "awcenter.E007"}.issubset(
                self.error_ids()
            )
        )

    def test_windows_native_mode_accepts_isolated_sqlite_without_proxy_trust(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            with (
                patch("awcenter.checks.sys.platform", "win32"),
                override_settings(
                    DEBUG=False,
                    AWCENTER_DEPLOYMENT_MODE="windows-native",
                    REPOSITORY_DIR=repository,
                    DATABASES={
                        "default": {
                            "ENGINE": "django.db.backends.sqlite3",
                            "NAME": root / "state" / "db.sqlite3",
                            "CONN_MAX_AGE": 0,
                        }
                    },
                    CACHES={
                        "default": {
                            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                            "LOCATION": str(root / "state" / "cache"),
                        }
                    },
                    PRIVATE_MEDIA_ROOT=root / "state" / "private-media",
                    STATIC_ROOT=root / "state" / "static",
                    MEDIA_ROOT=root / "state" / "media",
                    MODEL_RUNTIME_DIR=root / "assets" / "ai-models",
                    CUSTOM_TEMPLATE_DIR=root / "assets" / "document-templates",
                    TRUST_PROXY_HEADERS=False,
                    TRUSTED_PROXY_COUNT=0,
                ),
            ):
                identifiers = self.error_ids()

        self.assertTrue(
            {
                "awcenter.E001",
                "awcenter.E007",
                "awcenter.E030",
                "awcenter.E031",
                "awcenter.E032",
                "awcenter.E033",
                "awcenter.E035",
                "awcenter.E036",
            }.isdisjoint(identifiers)
        )

    @override_settings(
        ALLOWED_HOSTS=["awcenter.internal"],
        FRONTEND_RESET_URL="https://awcenter.internal:8443/app/login",
        FRONTEND_INVITATION_URL="https://awcenter.internal:8443/app/invite",
    )
    def test_frontend_capability_urls_accept_an_allowed_https_host_with_port(self):
        self.assertEqual(_frontend_capability_url_checks(), [])

    def test_frontend_capability_urls_fail_closed(self):
        invalid_reset_urls = (
            "http://awcenter.internal/app/login",
            "https://user:secret@awcenter.internal/app/login",
            "https://awcenter.internal/app/login?source=email",
            "https://awcenter.internal/app/login#token",
            "https://awcenter.internal/app/../login",
            "https://awcenter.internal/app/%2e%2e/login",
            "https://awcenter.internal/app/invite",
            "https://unlisted.internal/app/login",
            "https://awcenter.internal:99999/app/login",
        )
        for value in invalid_reset_urls:
            with self.subTest(value=value):
                with override_settings(
                    ALLOWED_HOSTS=["awcenter.internal"],
                    FRONTEND_RESET_URL=value,
                    FRONTEND_INVITATION_URL="https://awcenter.internal/app/invite",
                ):
                    self.assertEqual(
                        [check.id for check in _frontend_capability_url_checks()],
                        ["awcenter.E025"],
                    )

    @override_settings(
        DEBUG=False,
        ALLOWED_HOSTS=["awcenter.internal"],
        FRONTEND_RESET_URL="http://awcenter.internal/app/login",
        FRONTEND_INVITATION_URL="https://awcenter.internal/app/invite",
    )
    def test_frontend_capability_validation_is_a_production_runtime_check(self):
        self.assertIn("awcenter.E025", self.error_ids())

    @override_settings(
        ALLOWED_HOSTS=["awcenter.internal"],
        FRONTEND_RESET_URL="https://awcenter.internal/app/login",
        FRONTEND_INVITATION_URL="https://other.internal/app/invite?unsafe=1",
    )
    def test_invitation_url_uses_its_own_path_and_host_validation(self):
        self.assertEqual(
            [check.id for check in _frontend_capability_url_checks()],
            ["awcenter.E026"],
        )
