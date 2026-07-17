"""Unit tests for the AW Center launcher."""

from __future__ import annotations

import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import launcher


def launcher_config(command: str = "install", mode: str = "online") -> launcher.LauncherConfig:
    """Return a complete launcher configuration for focused unit tests."""
    return launcher.build_config(
        command=command,
        mode=mode,
        offline_dir=Path("/tmp/offline"),
        offline_zip=Path("/tmp/offline.zip"),
        changes_zip=Path("/tmp/changes.zip"),
        skip_frontend=False,
        skip_backend=False,
        fix_migrations=False,
        host="127.0.0.1",
        backend_port=8000,
        frontend_port=5173,
        no_backend_reload=False,
        ignore_packages=False,
        run_profile="development",
        collect_static=False,
    )


class LauncherTests(unittest.TestCase):
    """Validate deterministic launcher behavior without external installs."""

    def test_executable_is_platform_aware(self) -> None:
        """Executable suffixes should follow the active operating system."""
        expected = "python.exe" if os.name == "nt" else "python"
        self.assertEqual(launcher.executable("python"), expected)

    def test_offline_pip_command_uses_local_wheels(self) -> None:
        """Offline backend installs must avoid package indexes."""
        config = launcher_config(mode="offline")
        command = launcher.pip_install_command(config)
        self.assertIn("--no-index", command)
        self.assertIn(Path("/tmp/offline") / "wheels", command)

    @mock.patch("launcher.is_online", return_value=True)
    def test_auto_mode_selects_online_when_probe_succeeds(self, _: mock.Mock) -> None:
        """Auto mode should use online workflow when network probe succeeds."""
        self.assertEqual(launcher.detect_mode("auto", Path("/tmp/offline")), "online")

    @mock.patch("launcher.offline_bundle_ready", return_value=True)
    @mock.patch("launcher.is_online", return_value=False)
    def test_auto_mode_selects_offline_when_bundle_exists(self, _: mock.Mock, __: mock.Mock) -> None:
        """Auto mode should use offline workflow when network fails and a bundle exists."""
        self.assertEqual(launcher.detect_mode("auto", Path("/tmp/offline")), "offline")

    def test_development_env_contains_safe_local_defaults(self) -> None:
        """Generated env defaults must be local-development only."""
        content = launcher.development_env_content()
        self.assertIn("DEBUG=True", content)
        self.assertIn("IPV4_ADDRESS=127.0.0.1", content)
        self.assertIn("DEV_SERVER_ORIGINS=http://localhost:5173", content)
        self.assertIn("CSRF_TRUSTED_ORIGINS=http://localhost:5173", content)
        self.assertNotIn("CORS_ALLOW_ALL_ORIGINS", content)


    def test_browser_host_replaces_wildcard_bind(self) -> None:
        """Browser URLs must never point to the non-routable 0.0.0.0 bind address."""
        self.assertEqual(launcher.browser_host("0.0.0.0"), "127.0.0.1")

    def test_development_origins_include_frontend_and_backend_ports(self) -> None:
        """Development CORS and CSRF origins should follow selected ports."""
        origins = launcher.development_origins("127.0.0.1", 8010, 5174)
        self.assertIn("http://localhost:5174", origins)
        self.assertIn("http://127.0.0.1:8010", origins)

    def test_python_version_rejects_python_39(self) -> None:
        """Unsupported interpreters should fail before creating a venv."""
        with self.assertRaisesRegex(RuntimeError, "Python 3.11\\+ is required"):
            launcher.ensure_python_version((3, 9, 13), "launcher interpreter")

    def test_python_version_accepts_python_311(self) -> None:
        """Python 3.11 should satisfy the launcher minimum."""
        launcher.ensure_python_version((3, 11, 0), "launcher interpreter")

    @mock.patch("launcher.virtual_environment_version", return_value=(3, 11, 0))
    @mock.patch("launcher.run")
    @mock.patch("launcher.venv_python")
    @mock.patch("launcher.current_python_version", return_value=(3, 11, 0))
    def test_virtual_environment_created_with_current_python(
        self, _: mock.Mock, venv_python_mock: mock.Mock, run_mock: mock.Mock, __: mock.Mock
    ) -> None:
        """Missing virtual environments should be created by the active interpreter."""
        fake_virtual_environment = Path("/tmp/missing-venv")
        venv_python_mock.return_value = fake_virtual_environment / "bin" / "python"

        with mock.patch.object(launcher, "VENV", fake_virtual_environment):
            launcher.ensure_virtual_environment()

        run_mock.assert_called_once()

    @mock.patch("launcher.virtual_environment_version", return_value=(3, 9, 13))
    @mock.patch("launcher.venv_python")
    @mock.patch("launcher.current_python_version", return_value=(3, 11, 0))
    def test_existing_virtual_environment_version_is_validated(
        self, _: mock.Mock, venv_python_mock: mock.Mock, __: mock.Mock
    ) -> None:
        """Existing virtual environments should not silently keep Python 3.9."""
        venv_python_mock.return_value = Path(__file__)
        with self.assertRaisesRegex(RuntimeError, "existing \\.venv uses Python 3.9.13"):
            launcher.ensure_virtual_environment()


class ProductionRunTests(unittest.TestCase):
    """Validate production run profile dispatch without starting servers."""

    @mock.patch("launcher.run_production_server")
    @mock.patch("launcher.run_development_servers")
    def test_production_profile_uses_production_runner(
        self, development_mock: mock.Mock, production_mock: mock.Mock
    ) -> None:
        """The run command should dispatch production separately from development."""
        config = launcher_config(command="run")
        config = replace(config, run_profile="production")
        launcher.run_application(config)
        production_mock.assert_called_once_with(config)
        development_mock.assert_not_called()

    @mock.patch("launcher.run_production_server")
    @mock.patch("launcher.run_development_servers")
    def test_development_profile_uses_development_runner(
        self, development_mock: mock.Mock, production_mock: mock.Mock
    ) -> None:
        """The default run profile should preserve existing development behavior."""
        config = launcher_config(command="run")
        launcher.run_application(config)
        development_mock.assert_called_once_with(config)
        production_mock.assert_not_called()

    @mock.patch("launcher.run")
    @mock.patch("launcher.ensure_frontend_build_artifacts")
    @mock.patch("launcher.ensure_production_env_values")
    @mock.patch("launcher.ensure_production_certificates")
    @mock.patch("launcher.configure_production_runtime_env")
    @mock.patch("launcher.ensure_existing_virtual_environment")
    def test_production_profile_always_collects_static(
        self,
        _: mock.Mock,
        __: mock.Mock,
        ___: mock.Mock,
        ____: mock.Mock,
        _____: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        """Production startup should collect static assets before Cheroot starts."""
        config = launcher_config(command="run")
        config = replace(config, run_profile="production")

        launcher.run_production_server(config)

        commands = [call.args[0] for call in run_mock.call_args_list]
        collectstatic_command = [
            launcher.venv_python(),
            "manage.py",
            "collectstatic",
            "--noinput",
        ]
        self.assertIn(collectstatic_command, commands)


if __name__ == "__main__":
    unittest.main()
