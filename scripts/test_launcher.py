"""Unit tests for the AW Center launcher."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

import launcher


class LauncherTests(unittest.TestCase):
    """Validate deterministic launcher behavior without external installs."""

    def test_executable_is_platform_aware(self) -> None:
        """Executable suffixes should follow the active operating system."""
        expected = "python.exe" if os.name == "nt" else "python"
        self.assertEqual(launcher.executable("python"), expected)

    def test_offline_pip_command_uses_local_wheels(self) -> None:
        """Offline backend installs must avoid package indexes."""
        config = launcher.LauncherConfig("install", "offline", Path("/tmp/offline"), False, False)
        command = launcher.pip_install_command(config)
        self.assertIn("--no-index", command)
        self.assertIn(str(Path("/tmp/offline") / "wheels"), command)

    @mock.patch("launcher.is_online", return_value=True)
    def test_auto_mode_selects_online_when_probe_succeeds(self, _: mock.Mock) -> None:
        """Auto mode should use online workflow when network probe succeeds."""
        self.assertEqual(launcher.detect_mode("auto"), "online")

    @mock.patch("launcher.is_online", return_value=False)
    def test_auto_mode_selects_offline_when_probe_fails(self, _: mock.Mock) -> None:
        """Auto mode should use offline workflow when network probe fails."""
        self.assertEqual(launcher.detect_mode("auto"), "offline")

    def test_development_env_contains_safe_local_defaults(self) -> None:
        """Generated env defaults must be local-development only."""
        content = launcher.development_env_content()
        self.assertIn("DEBUG=True", content)
        self.assertIn("IPV4_ADDRESS=127.0.0.1", content)
        self.assertNotIn("CORS_ALLOW_ALL_ORIGINS", content)

    def test_python_version_rejects_python_39(self) -> None:
        """Unsupported interpreters should fail before creating a venv."""
        with self.assertRaisesRegex(RuntimeError, "Python 3.11\\+ is required"):
            launcher.ensure_python_version((3, 9, 13), "launcher interpreter")

    def test_python_version_accepts_python_311(self) -> None:
        """Python 3.11 should satisfy the launcher minimum."""
        launcher.ensure_python_version((3, 11, 0), "launcher interpreter")

    @mock.patch("launcher.run")
    @mock.patch("launcher.venv_python")
    @mock.patch("launcher.current_python_version", return_value=(3, 11, 0))
    def test_virtual_environment_created_with_current_python(
        self, _: mock.Mock, venv_python_mock: mock.Mock, run_mock: mock.Mock
    ) -> None:
        """Missing virtual environments should be created by the active interpreter."""
        venv_python_mock.return_value = Path("/tmp/missing-venv/bin/python")
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


if __name__ == "__main__":
    unittest.main()
