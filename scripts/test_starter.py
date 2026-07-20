"""Unit tests for the AW Center starter helpers."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from scripts import starter_core as starter


class StarterHelperTests(unittest.TestCase):
    """Validate deterministic starter helper behavior."""

    def test_backend_env_template_contains_safe_debug_defaults(self) -> None:
        """The generated development env must stay local and non-production."""
        content = starter.backend_env_template()
        self.assertIn("DEBUG=True", content)
        self.assertIn("IPV4_ADDRESS=127.0.0.1", content)
        self.assertIn("DEV_SERVER_ORIGINS=http://localhost:5173", content)
        self.assertIn("CSRF_TRUSTED_ORIGINS=http://localhost:5173", content)
        self.assertNotIn("CORS_ALLOW_ALL_ORIGINS", content)

    def test_executable_name_adds_windows_suffix_only_on_windows(self) -> None:
        """Executable naming should be platform aware."""
        expected = "python.exe" if os.name == "nt" else "python"
        self.assertEqual(starter.executable_name("python"), expected)

    @mock.patch("shutil.which", return_value="/usr/bin/node")
    def test_command_exists_reports_available_tool(self, which_mock: mock.Mock) -> None:
        """Command checks should include the resolved executable path."""
        result = starter.command_exists("node")
        self.assertTrue(result.available)
        self.assertEqual(result.detail, "/usr/bin/node")
        which_mock.assert_called_once_with("node")

    def test_fail_when_missing_raises_for_missing_tool(self) -> None:
        """Missing required tools must fail before installation or startup."""
        results = [starter.CommandResult("npm", False, "not found")]
        with self.assertRaisesRegex(RuntimeError, "npm"):
            starter.fail_when_missing(results)

    @mock.patch.object(starter, "wait_for_servers")
    @mock.patch.object(starter, "start_process")
    @mock.patch.object(starter, "ensure_backend_env")
    def test_start_launches_job_worker(
        self, _ensure_env: mock.Mock, start_process: mock.Mock, wait: mock.Mock
    ) -> None:
        """The documented starter must consume durable queued jobs."""
        processes = [mock.sentinel.backend, mock.sentinel.worker, mock.sentinel.frontend]
        start_process.side_effect = processes

        starter.start_servers("127.0.0.1", 8000, 5173)

        commands = [call.args[0] for call in start_process.call_args_list]
        self.assertIn(starter.worker_command(), commands)
        wait.assert_called_once_with(processes)


if __name__ == "__main__":
    unittest.main()
