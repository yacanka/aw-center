import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import environ
from django.core.cache.backends.filebased import FileBasedCache
from django.test import SimpleTestCase

from awcenter.settings import load_environment_files


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def read_env_values(path):
    """Read the simple KEY=VALUE shape used by committed env templates."""
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise AssertionError(f"invalid env template line: {raw_line}")
        if key in values:
            raise AssertionError(f"duplicate env template key: {key}")
        values[key] = value
    return values


class EnvironmentFilePrecedenceTests(SimpleTestCase):
    """Protect OS environment values from dotenv profile replacement."""

    def test_selected_profile_overrides_base_file_but_not_process_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            (base_dir / ".env").write_text(
                "AWCENTER_ENV_FILE=.env.production\n"
                "FROM_PROFILE=base\n"
                "PROCESS_VALUE=base\n",
                encoding="utf-8",
            )
            (base_dir / ".env.production").write_text(
                "FROM_PROFILE=production\n"
                "PROCESS_VALUE=profile\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PROCESS_VALUE": "process"}, clear=True):
                selected = load_environment_files(environ.Env(), base_dir)

                self.assertEqual(selected, base_dir / ".env.production")
                self.assertEqual(os.environ["FROM_PROFILE"], "production")
                self.assertEqual(os.environ["PROCESS_VALUE"], "process")

    def test_os_selected_profile_keeps_process_environment_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            (base_dir / "custom.env").write_text(
                "PROCESS_VALUE=profile\nPROFILE_ONLY=value\n",
                encoding="utf-8",
            )
            process_environment = {
                "AWCENTER_ENV_FILE": "custom.env",
                "PROCESS_VALUE": "process",
            }
            with patch.dict(os.environ, process_environment, clear=True):
                selected = load_environment_files(environ.Env(), base_dir)

                self.assertEqual(selected, base_dir / "custom.env")
                self.assertEqual(os.environ["PROCESS_VALUE"], "process")
                self.assertEqual(os.environ["PROFILE_ONLY"], "value")


class DevelopmentEnvironmentTemplateTests(SimpleTestCase):
    """Keep the committed local profile safe and explicit."""

    def test_example_is_self_contained_for_local_and_offline_setup(self):
        example = read_env_values(REPOSITORY_ROOT / "backend/.env.example")

        self.assertEqual(example["DEBUG"], "True")
        self.assertEqual(example["AWCENTER_DEPLOYMENT_MODE"], "development")
        self.assertTrue(example["DATABASE_URL"].startswith("sqlite:///"))
        self.assertNotIn("AWCENTER_ENV_FILE", example)
        self.assertNotIn("SECRET_KEY", example)

    def test_development_templates_are_local_only_and_secret_free(self):
        templates = (
            REPOSITORY_ROOT / "backend/.env.example",
            REPOSITORY_ROOT / "backend/.env.development",
        )
        for template in templates:
            with self.subTest(template=template.name):
                self.assert_local_template_is_safe(read_env_values(template))

    def assert_local_template_is_safe(self, values):
        self.assertEqual(values["DEBUG"], "True")
        self.assertEqual(values["AWCENTER_DEPLOYMENT_MODE"], "development")
        self.assertTrue(values["DATABASE_URL"].startswith("sqlite:///"))
        self.assertEqual(values["CACHE_DIRECTORY"], "")
        self.assertEqual(values["TRUST_PROXY_HEADERS"], "False")
        self.assertEqual(values["SESSION_COOKIE_SECURE"], "False")
        self.assertEqual(values["CSRF_COOKIE_SECURE"], "False")
        for feature in (
            "DOCPROOF_ENABLED",
            "DOORS_ENABLED",
            "JIRA_ENABLED",
            "NUMARATOR_ENABLED",
            "TEAMCENTER_ENABLED",
        ):
            self.assertEqual(values[feature].casefold(), "false")
        for credential in (
            "DOCPROOF_USERNAME",
            "DOCPROOF_PASSWORD",
            "JIRA_SESSION_ENCRYPTION_KEY",
            "NUMARATOR_API_KEY",
            "TEAMCENTER_USERNAME",
            "TEAMCENTER_PASSWORD",
            "TEAMCENTER_JSESSIONID",
            "TEAMCENTER_XSRF_TOKEN",
        ):
            self.assertEqual(values.get(credential, ""), "")
        self.assertNotIn("SECRET_KEY", values)
        self.assertNotIn("USE_X_FORWARDED_HOST", values)


class WindowsProductionEnvironmentTemplateTests(SimpleTestCase):
    """Keep the tracked production example aligned with the native runtime."""

    def test_template_uses_isolated_sqlite_shared_file_cache_and_doors_worker(self):
        values = read_env_values(REPOSITORY_ROOT / "backend/.env.production")

        self.assertEqual(values["AWCENTER_DEPLOYMENT_MODE"], "windows-native")
        self.assertEqual(values["DEBUG"], "False")
        self.assertTrue(values["DATABASE_URL"].startswith("sqlite:///C:/Users/"))
        self.assertEqual(values["DATABASE_CONN_MAX_AGE"], "0")
        self.assertEqual(values["CACHE_URL"], "")
        self.assertTrue(values["CACHE_DIRECTORY"].startswith("C:/Users/"))
        self.assertEqual(values["TRUST_PROXY_HEADERS"], "False")
        self.assertEqual(values["DOORS_EXECUTION_MODE"], "worker")
        self.assertEqual(values["DOORS_RUNNER_TOKEN"], "")
        self.assertIn("/assets/sets/", values["MODEL_RUNTIME_DIR"])
        self.assertIn("/assets/sets/", values["CUSTOM_TEMPLATE_DIR"])

    def test_file_cache_state_is_visible_to_separate_cache_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            web_cache = FileBasedCache(directory, {})
            worker_cache = FileBasedCache(directory, {})

            web_cache.set("ephemeral-session", "encrypted-value", timeout=60)

            self.assertEqual(worker_cache.get("ephemeral-session"), "encrypted-value")
