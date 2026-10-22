import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import environ
from cryptography.fernet import Fernet
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

    def test_external_profile_selected_by_pointer_preserves_process_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory) / "backend"
            base_dir.mkdir()
            external = Path(directory) / "private profile.env"
            external.write_text("FROM_PRIVATE=private\nPROCESS_VALUE=file\n", encoding="utf-8")
            (base_dir / ".env").write_text(
                f'AWCENTER_ENV_FILE="{external.as_posix()}"\n', encoding="utf-8"
            )
            with patch.dict(os.environ, {"PROCESS_VALUE": "process"}, clear=True):
                selected = load_environment_files(environ.Env(), base_dir)

                self.assertEqual(selected, external)
                self.assertEqual(os.environ["FROM_PRIVATE"], "private")
                self.assertEqual(os.environ["PROCESS_VALUE"], "process")


class ExplicitKeyStartupTests(SimpleTestCase):
    """Exercise fresh settings imports without inheriting this machine's credentials."""

    def load_settings(self, values, *, overrides=None):
        script = """
import hashlib
import json
from django.core.exceptions import ImproperlyConfigured
try:
    from awcenter import settings
except ImproperlyConfigured as error:
    print(str(error))
    raise SystemExit(1)
print(json.dumps({
    'secret_digest': hashlib.sha256(settings.SECRET_KEY.encode()).hexdigest(),
    'jira_digest': hashlib.sha256(settings.JIRA_SESSION_ENCRYPTION_KEY.encode()).hexdigest(),
    'docproof_ca': str(settings.DOCPROOF_CERTIFICATE_FILE) if settings.DOCPROOF_CERTIFICATE_FILE else None,
    'dcc_policy': settings.GOKBEY_DCC_POLICY_FILE,
    'project_configuration': settings.PROJECT_CONFIGURATION_FILE,
    'ddf_policy': settings.DDF_ASSESSMENT_POLICY_FILE,
    'database': settings.DATABASES['default']['NAME'],
    'artifacts': str(settings.PRIVATE_MEDIA_ROOT),
}))
"""
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory) / "private.env"
            external.write_text(values, encoding="utf-8")
            environment = {
                name: value for name, value in os.environ.items()
                if name in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}
            }
            environment["AWCENTER_ENV_FILE"] = str(external)
            environment.update(overrides or {})
            return subprocess.run(
                [sys.executable, "-c", script], cwd=REPOSITORY_ROOT / "backend",
                env=environment, capture_output=True, text=True, check=False,
            )

    def test_ca_and_policy_paths_are_explicit_and_process_values_take_precedence(self):
        initial = self.load_settings("DEBUG=True\nSECRET_KEY=synthetic-startup-secret\n")
        self.assertEqual(initial.returncode, 0, initial.stderr)
        self.assertIsNone(json.loads(initial.stdout)["docproof_ca"])
        self.assertEqual(json.loads(initial.stdout)["dcc_policy"], "")
        result = self.load_settings(
            "SECRET_KEY=synthetic-startup-secret\nDOCPROOF_CERTIFICATE_FILE=/private/file-ca.pem\n"
            "GOKBEY_DCC_POLICY_FILE=/private/file-policy.json\n",
            overrides={"DOCPROOF_CERTIFICATE_FILE": "/private/process-ca.pem",
                       "GOKBEY_DCC_POLICY_FILE": "/private/process-policy.json"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["docproof_ca"], str(Path("/private/process-ca.pem")))
        self.assertEqual(json.loads(result.stdout)["dcc_policy"], "/private/process-policy.json")

    def test_workflow_paths_preserve_process_precedence_and_restart_stability(self):
        values = ("SECRET_KEY=synthetic-startup-secret\n"
                  "PROJECT_CONFIGURATION_FILE=/private/env-projects.json\n"
                  "DDF_ASSESSMENT_POLICY_FILE=/private/env-ddf.json\n")
        overrides = {"PROJECT_CONFIGURATION_FILE": "/private/process-projects.json",
                     "DDF_ASSESSMENT_POLICY_FILE": "/private/process-ddf.json"}
        first = self.load_settings(values, overrides=overrides)
        second = self.load_settings(values, overrides=overrides)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertEqual(json.loads(first.stdout)["project_configuration"], overrides["PROJECT_CONFIGURATION_FILE"])
        self.assertEqual(json.loads(first.stdout)["ddf_policy"], overrides["DDF_ASSESSMENT_POLICY_FILE"])

    def test_missing_or_blank_secret_stops_startup_even_in_debug(self):
        for entry in ("", "SECRET_KEY=\n", "SECRET_KEY='   '\n"):
            with self.subTest(entry=entry):
                result = self.load_settings("DEBUG=True\n" + entry)
                self.assertEqual(result.returncode, 1)
                self.assertIn("SECRET_KEY", result.stdout)
                self.assertEqual(result.stderr, "")

    def test_jira_requires_an_explicit_valid_key_before_startup(self):
        for debug in ("True", "False"):
            for key in ("", "not-a-fernet-key", "non-ascii-ş"):
                with self.subTest(debug=debug, key=key):
                    result = self.load_settings(
                        f"DEBUG={debug}\nSECRET_KEY=synthetic-startup-secret\n"
                        f"JIRA_ENABLED=True\nJIRA_SESSION_ENCRYPTION_KEY={key}\n"
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("JIRA_SESSION_ENCRYPTION_KEY", result.stdout)
                    if key:
                        self.assertNotIn(key, result.stdout + result.stderr)
                    self.assertEqual(result.stderr, "")

    def test_disabled_jira_does_not_require_an_encryption_key(self):
        result = self.load_settings(
            "DEBUG=True\nSECRET_KEY=synthetic-startup-secret\nJIRA_ENABLED=False\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_private_configuration_is_stable_and_keeps_data_paths(self):
        key = Fernet.generate_key().decode("ascii")
        values = (
            "DEBUG=True\nSECRET_KEY=synthetic-startup-secret\nJIRA_ENABLED=True\n"
            f"JIRA_SESSION_ENCRYPTION_KEY={key}\n"
            "DATABASE_URL=sqlite:///unchanged.sqlite3\nPRIVATE_MEDIA_ROOT=unchanged-private\n"
        )
        first = self.load_settings(values)
        second = self.load_settings(values)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        resolved = json.loads(first.stdout)
        self.assertEqual(resolved["database"], "unchanged.sqlite3")
        self.assertEqual(Path(resolved["artifacts"]), REPOSITORY_ROOT / "backend/unchanged-private")
        overridden = self.load_settings(values, overrides={"SECRET_KEY": "synthetic-process-secret"})
        self.assertEqual(overridden.returncode, 0, overridden.stderr)
        self.assertNotEqual(json.loads(overridden.stdout)["secret_digest"], resolved["secret_digest"])


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
        self.assertEqual(values["JOB_JSON_MAX_INPUT_BYTES"], "1048576")
        self.assertIn("/assets/sets/", values["MODEL_RUNTIME_DIR"])
        self.assertIn("/assets/sets/", values["CUSTOM_TEMPLATE_DIR"])

    def test_file_cache_state_is_visible_to_separate_cache_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            web_cache = FileBasedCache(directory, {})
            worker_cache = FileBasedCache(directory, {})

            web_cache.set("ephemeral-session", "encrypted-value", timeout=60)

            self.assertEqual(worker_cache.get("ephemeral-session"), "encrypted-value")
