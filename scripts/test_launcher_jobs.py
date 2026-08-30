"""Regression tests for launcher-owned durable job workers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.launcher.model import Project, Scope
from scripts.launcher.runtime import dev
from scripts.test_launcher import create_project


def add_worker_command(project: Project) -> None:
    """Add the conventional durable worker command to a synthetic project."""

    command = project.backend / "jobs/management/commands/run_job_worker.py"
    command.parent.mkdir(parents=True)
    command.write_text("", encoding="utf-8")


def add_auxiliary_worker_commands(project: Project) -> None:
    """Add notification and cleanup lifecycle commands to a synthetic project."""

    for relative_path in (
        "compliance/management/commands/run_compdoc_notification_worker.py",
        "jobs/management/commands/run_job_cleanup_worker.py",
    ):
        command = project.backend / relative_path
        command.parent.mkdir(parents=True, exist_ok=True)
        command.write_text("", encoding="utf-8")


class LauncherJobWorkerTests(unittest.TestCase):
    """Ensure every launcher runtime mode consumes durable queues."""

    @mock.patch("scripts.launcher.runtime.supervise")
    @mock.patch("scripts.launcher.job_worker.start")
    @mock.patch("scripts.launcher.runtime.start")
    @mock.patch("scripts.launcher.runtime.ensure_virtual_environment")
    @mock.patch("scripts.launcher.runtime.require_port")
    def test_development_starts_discovered_worker(
        self, _port, _environment, backend_start, worker_start, supervise
    ) -> None:
        """Development supervision must include the worker with Django."""

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            add_worker_command(project)
            dev(project, Scope(frontend=False), host="127.0.0.1", backend_port=8000,
                frontend_port=5173, no_backend_reload=False, migrate=False)

        self.assertIn("run_job_worker", worker_start.call_args.args[0])
        self.assertEqual(worker_start.call_args.kwargs["extra_env"]["PORT"], "8000")
        supervise.assert_called_once_with([backend_start.return_value, worker_start.return_value])

    @mock.patch("scripts.launcher.runtime.supervise")
    @mock.patch("scripts.launcher.job_worker.start")
    @mock.patch("scripts.launcher.runtime.start")
    @mock.patch("scripts.launcher.runtime.ensure_virtual_environment")
    @mock.patch("scripts.launcher.runtime.require_port")
    def test_development_supervises_notification_and_cleanup_lifecycles(
        self, _port, _environment, backend_start, worker_start, supervise
    ) -> None:
        """Discovered background responsibilities run as separate children."""

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            add_worker_command(project)
            add_auxiliary_worker_commands(project)
            dev(
                project,
                Scope(frontend=False),
                host="127.0.0.1",
                backend_port=8000,
                frontend_port=5173,
                no_backend_reload=False,
                migrate=False,
            )

        commands = [call.args[0] for call in worker_start.call_args_list]
        self.assertEqual(len(commands), 3)
        self.assertTrue(any("run_job_worker" in command for command in commands))
        self.assertTrue(any("run_compdoc_notification_worker" in command for command in commands))
        self.assertTrue(any("run_job_cleanup_worker" in command for command in commands))
        supervise.assert_called_once_with(
            [backend_start.return_value, *[worker_start.return_value] * 3]
        )


if __name__ == "__main__":
    unittest.main()
