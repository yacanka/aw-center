"""Regression tests for launcher-owned durable job workers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from scripts.launcher.model import Project, Scope
from scripts.launcher.runtime import dev, prod
from scripts.launcher.job_worker import start_job_workers
from scripts.launcher_test_support import create_project


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

        worker_command = worker_start.call_args.args[0]
        self.assertIn("run_job_worker", worker_command)
        self.assertIn("--include-doors-if-enabled", worker_command)
        self.assertEqual(worker_start.call_args.kwargs["extra_env"]["PORT"], "8000")
        supervise.assert_called_once_with([backend_start.return_value, worker_start.return_value])

    @mock.patch("scripts.launcher.runtime.supervise")
    @mock.patch("scripts.launcher.job_worker.start")
    @mock.patch("scripts.launcher.runtime.start")
    @mock.patch("scripts.launcher.runtime.ensure_virtual_environment")
    @mock.patch("scripts.launcher.runtime.require_port")
    def test_development_can_exclude_doors_queue(
        self, _port, _environment, backend_start, worker_start, supervise
    ) -> None:
        """The opt-out must leave the development worker on local queues only."""

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            add_worker_command(project)
            dev(
                project,
                Scope(frontend=False),
                host="127.0.0.1",
                backend_port=8000,
                frontend_port=5173,
                no_backend_reload=False,
                migrate=False,
                exclude_doors=True,
            )

        worker_command = worker_start.call_args.args[0]
        self.assertNotIn("--include-doors", worker_command)
        self.assertNotIn("--include-doors-if-enabled", worker_command)
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
        self.assertEqual(backend_start.call_args.kwargs["extra_env"]["NUMARATOR_API_KEY"], "")
        for call in worker_start.call_args_list:
            if "run_job_worker" in call.args[0]:
                self.assertNotIn("NUMARATOR_API_KEY", call.kwargs["extra_env"])
            else:
                self.assertEqual(call.kwargs["extra_env"]["NUMARATOR_API_KEY"], "")
        supervise.assert_called_once_with(
            [backend_start.return_value, *[worker_start.return_value] * 3]
        )


class LauncherStartupCleanupTests(unittest.TestCase):
    """Failed startup must not leave a live process outside supervision."""

    def sleeping_child(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

        def cleanup():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)

        self.addCleanup(cleanup)
        return process

    def test_partial_worker_startup_stops_already_started_workers(self):
        for failure in (OSError("startup failed"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as temporary:
                project = create_project(Path(temporary))
                add_worker_command(project)
                add_auxiliary_worker_commands(project)
                child = self.sleeping_child()
                with mock.patch("scripts.launcher.job_worker.start", side_effect=[child, failure]):
                    with self.assertRaises(type(failure)):
                        start_job_workers(project, {})
                self.assertIsNotNone(child.poll(), "The first worker survived failed startup")

    def test_production_worker_startup_failure_stops_backend(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as patches:
            project = create_project(Path(temporary))
            child = self.sleeping_child()
            for name in (
                "require_windows_production", "ensure_virtual_environment",
                "require_production_host", "require_port", "require_external_file",
                "validate_tls_identity", "django",
            ):
                patches.enter_context(mock.patch(f"scripts.launcher.runtime.{name}"))
            patches.enter_context(mock.patch(
                "scripts.launcher.runtime.start_production_backend", return_value=child,
            ))
            patches.enter_context(mock.patch(
                "scripts.launcher.runtime.start_job_workers", side_effect=OSError("startup failed"),
            ))
            with self.assertRaises(OSError):
                prod(
                    project, host="192.0.2.10", port=443,
                    env_file=Path(temporary) / "production.env",
                    certificate_file=Path(temporary) / "tls.crt",
                    private_key_file=Path(temporary) / "tls.key",
                    exclude_doors=False, migrate=False,
                )
            self.assertIsNotNone(child.poll(), "The backend survived failed startup")

    def test_development_frontend_startup_failure_stops_backend_and_workers(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as patches:
            project = create_project(Path(temporary))
            backend, worker = self.sleeping_child(), self.sleeping_child()
            patches.enter_context(mock.patch("scripts.launcher.runtime.require_runtime_ports"))
            patches.enter_context(mock.patch("scripts.launcher.runtime.start_backend", return_value=backend))
            patches.enter_context(mock.patch("scripts.launcher.runtime.start_job_workers", return_value=[worker]))
            patches.enter_context(mock.patch("scripts.launcher.runtime.start_frontend", side_effect=OSError("startup failed")))
            with self.assertRaises(OSError):
                dev(
                    project, Scope(), host="127.0.0.1", backend_port=8000,
                    frontend_port=5173, no_backend_reload=True, migrate=False,
                )
            self.assertIsNotNone(backend.poll(), "The backend survived failed startup")
            self.assertIsNotNone(worker.poll(), "The worker survived failed startup")


class LauncherProcessTreeTests(unittest.TestCase):
    """A failed/exited launcher child must not leave its descendants running."""

    def test_shutdown_stops_descendants_even_after_the_parent_exits(self):
        from scripts.launcher.process import start, terminate

        for exit_parent in (False, True):
            with self.subTest(exit_parent=exit_parent), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                marker = root / 'heartbeat'
                ready = root / 'ready'
                leaf_code = """
import os, signal, sys, time
from pathlib import Path
if os.name != 'nt':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
marker = Path(sys.argv[1])
for index in range(3000):
    marker.write_text(str(index))
    time.sleep(0.01)
"""
                parent_code = """
import json, subprocess, sys, time
from pathlib import Path
leaf = subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])
while not Path(sys.argv[2]).exists():
    time.sleep(0.01)
Path(sys.argv[3]).write_text(json.dumps(leaf.pid))
if sys.argv[4] != 'exit':
    time.sleep(30)
"""
                process = start([
                    sys.executable, '-c', parent_code, leaf_code, str(marker), str(ready),
                    'exit' if exit_parent else 'wait',
                ], root)
                leaf_pid = None
                try:
                    deadline = time.monotonic() + 5
                    while not ready.exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(ready.exists(), 'Synthetic descendant did not start')
                    leaf_pid = json.loads(ready.read_text())
                    if exit_parent:
                        process.wait(timeout=5)
                    terminate([process])
                    # Observe execution, not PID existence (a stopped zombie can retain a PID).
                    stopped_at = marker.read_text()
                    time.sleep(0.15)
                    self.assertEqual(marker.read_text(), stopped_at, 'Descendant survived launcher cleanup')
                    self.assertIsNotNone(process.poll())
                    terminate([process])  # Cleanup is safe to repeat.
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
                    if leaf_pid:
                        try:
                            os.kill(leaf_pid, 9 if os.name != 'nt' else 15)
                        except ProcessLookupError:
                            pass
                        except OSError as error:
                            # Windows reports an already terminated PID as ERROR_INVALID_PARAMETER.
                            if os.name != 'nt' or error.winerror != 87:
                                raise

    def test_unreaped_exited_child_does_not_prevent_sibling_cleanup(self):
        from scripts.launcher.process import start, terminate

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            done = root / "done"
            exited = start([sys.executable, "-c",
                            "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", str(done)], root)
            sibling = start([sys.executable, "-c", "import time; time.sleep(30)"], root)
            try:
                deadline = time.monotonic() + 5
                while not done.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(done.exists())
                time.sleep(0.15)  # Leave the finished child unreaped intentionally.
                terminate([exited, sibling])
                self.assertIsNotNone(exited.poll())
                self.assertIsNotNone(sibling.poll())
            finally:
                for process in (exited, sibling):
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)

    def test_posix_start_isolates_children_from_the_launchers_process_group(self):
        if os.name == 'nt':
            self.skipTest('POSIX process-group contract')
        from scripts.launcher.process import start, terminate

        with tempfile.TemporaryDirectory() as directory:
            process = start([sys.executable, '-c', 'import time; time.sleep(30)'], Path(directory))
            try:
                self.assertEqual(os.getpgid(process.pid), process.pid)
                self.assertNotEqual(os.getpgid(process.pid), os.getpgrp())
            finally:
                terminate([process])


class LauncherWindowsContainmentTests(unittest.TestCase):
    """The Windows launch gate fails closed before any requested command starts."""

    def test_command_waits_for_containment_before_gate_release(self):
        from scripts.launcher.process import _start_windows, terminate

        events = []
        process = mock.Mock()
        process.poll.return_value = 0
        process._handle = 42
        process.stdin.write.side_effect = lambda data: events.append(('gate', data))
        job = mock.Mock()
        def assign(handle):
            events.append(('assign', handle))
            return job
        with mock.patch('scripts.launcher.process.subprocess.Popen', return_value=process) as popen, \
             mock.patch('scripts.launcher.process.subprocess.CREATE_NEW_PROCESS_GROUP', 512, create=True), \
             mock.patch('scripts.launcher.windows_job.WindowsJob', side_effect=assign):
            result = _start_windows(['python', '-V'], Path.cwd(), {})
        self.assertIs(result, process)
        self.assertEqual(events, [('assign', 42), ('gate', b'go\n')])
        self.assertEqual(popen.call_args.args[0][-2:], ['python', '-V'])
        self.assertEqual(popen.call_args.kwargs['creationflags'], 512)
        process._launcher_group = None
        terminate([process])
        job.terminate.assert_called_once()
        job.wait_for_exit.assert_called_once()
        job.close.assert_called_once()

    def test_assignment_failure_does_not_release_gate_and_reaps_bootstrap(self):
        from scripts.launcher.process import _start_windows

        process = mock.Mock()
        process._launcher_job = None
        process._launcher_group = None
        process.poll.side_effect = [None, None, 0, 0]
        with mock.patch('scripts.launcher.process.subprocess.Popen', return_value=process), \
             mock.patch('scripts.launcher.process.subprocess.CREATE_NEW_PROCESS_GROUP', 512, create=True), \
             mock.patch('scripts.launcher.windows_job.WindowsJob', side_effect=OSError('assignment failed')):
            with self.assertRaisesRegex(OSError, 'assignment failed'):
                _start_windows(['python', '-V'], Path.cwd(), {})
        process.stdin.write.assert_not_called()
        process.stdin.close.assert_called_once()
        process.terminate.assert_called_once()
        process.wait.assert_called_once()

    def test_broken_gate_pipe_still_releases_the_owned_job(self):
        from scripts.launcher.process import _start_windows

        process = mock.Mock()
        process._launcher_group = None
        process.poll.return_value = 0
        process.stdin.flush.side_effect = BrokenPipeError("closed gate")
        process.stdin.close.side_effect = BrokenPipeError("closed gate")
        job = mock.Mock()
        with mock.patch("scripts.launcher.process.subprocess.Popen", return_value=process), \
             mock.patch("scripts.launcher.process.subprocess.CREATE_NEW_PROCESS_GROUP", 512, create=True), \
             mock.patch("scripts.launcher.windows_job.WindowsJob", return_value=job):
            with self.assertRaises(BrokenPipeError):
                _start_windows(["python", "-V"], Path.cwd(), {})
        job.terminate.assert_called_once()
        job.close.assert_called_once()
        process.wait.assert_called_once()

    def test_windows_job_waits_for_descendants_with_a_bounded_deadline(self):
        from scripts.launcher.windows_job import WindowsJob

        job = WindowsJob.__new__(WindowsJob)
        job.has_processes = mock.Mock(side_effect=[True, False])
        with mock.patch("scripts.launcher.windows_job.sleep") as sleep:
            self.assertTrue(job.wait_for_exit(1))
        sleep.assert_called_once_with(0.01)
        job.has_processes = mock.Mock(return_value=True)
        self.assertFalse(job.wait_for_exit(0))

    def test_bootstrap_does_not_execute_command_when_gate_closes(self):
        from scripts.launcher import child_bootstrap

        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'started'
            command = [sys.executable, child_bootstrap.__file__, sys.executable, '-c',
                       'import pathlib,sys; pathlib.Path(sys.argv[1]).touch()', str(marker)]
            blocked = subprocess.run(command, input=b'', check=False)
            self.assertEqual(blocked.returncode, 1)
            self.assertFalse(marker.exists())
            allowed = subprocess.run(command, input=b'go\n', check=False)
            self.assertEqual(allowed.returncode, 0)
            self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
