import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event, Thread
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
from urllib.parse import quote, urlsplit

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionResult
from jobs.models import JobStatus
from jobs.services import create_job, request_cancellation
from jobs.process_bootstrap import bootstrap_executor_process
from jobs.worker import claim_next_job, execute_claimed_job, start_executor_process
from jobs.worker import persist_result as real_persist_result


def isolated_success_executor(_job):
    """Produce a child-owned artifact for the process-boundary tests."""

    output = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    output.write(b"isolated-result")
    output.close()
    return JobExecutionResult(Path(output.name), "result.txt")


def isolated_slow_executor(_job):
    """Stay alive long enough for the parent to enforce cancellation or timeout."""

    time.sleep(30)
    return isolated_success_executor(_job)


def isolated_scratch_executor(job):
    """Allocate both shared-helper and library-style scratch before termination."""

    source = materialize_job_input(job)
    output = temporary_output(".txt")
    output.write_bytes(b"private scratch result")
    with tempfile.TemporaryDirectory(prefix="executor-library-") as directory:
        Path(directory, "intermediate.txt").write_bytes(b"private intermediate")
        Path(job.parameters["scratch_marker"]).write_text(
            json.dumps([str(source), str(output), directory]), encoding="utf-8"
        )
        mode = job.parameters["scratch_mode"]
        if mode == "crash":
            os._exit(12)
        if mode == "success":
            source.unlink(missing_ok=True)
            return JobExecutionResult(output, "result.txt")
        if mode == "cancel":
            request_cancellation(job)
        try:
            time.sleep(30)
        finally:
            source.unlink(missing_ok=True)
            output.unlink(missing_ok=True)


def isolated_nested_executor(job):
    """Create a real child/grandchild tree that outlives a killed executor."""

    marker = str(job.parameters["tree_marker"])
    code = """
import json, os, signal, subprocess, sys, time
if os.name != "nt":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
leaf_code = "import os, signal, time; " + (
    "signal.signal(signal.SIGTERM, signal.SIG_IGN); " if os.name != "nt" else ""
) + "time.sleep(60)"
leaf = subprocess.Popen([sys.executable, "-c", leaf_code],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
with open(sys.argv[1], "w") as output:
    json.dump([os.getpid(), leaf.pid], output)
time.sleep(60)
"""
    subprocess.Popen(
        [sys.executable, "-c", code, marker],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 5
    while not Path(marker).exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not Path(marker).exists():
        raise RuntimeError("Nested fixture did not start")
    mode = job.parameters["tree_mode"]
    if mode == "crash":
        os._exit(12)
    if mode == "success":
        return isolated_success_executor(job)
    if mode == "cancel":
        request_cancellation(job)
    time.sleep(30)
    return isolated_success_executor(job)


def isolated_resolver(kind):
    """Resolve only test kinds without accepting a dotted path from job data."""

    if kind.endswith(".scratch"):
        return isolated_scratch_executor
    if kind.endswith(".nested"):
        return isolated_nested_executor
    if kind.endswith(".slow"):
        return isolated_slow_executor
    return isolated_success_executor


class IsolatedWorkerTests(TransactionTestCase):
    """Exercise the production parent/child execution boundary against durable state."""

    def setUp(self):
        self.private_root = Path(tempfile.mkdtemp())
        self.settings_override = override_settings(PRIVATE_MEDIA_ROOT=self.private_root)
        self.settings_override.enable()
        environment_values = {"PRIVATE_MEDIA_ROOT": str(self.private_root)}
        if connection.vendor == "sqlite":
            # Spawn reloads settings instead of inheriting the parent's test DB.
            # Export the actual test database path, never the source DB.
            database_name = connection.settings_dict["NAME"]
            self.assertFalse(
                connection.creation.is_in_memory_db(database_name),
                "Spawn regressions require a file-backed SQLite test database.",
            )
            database_path = Path(database_name).resolve()
            environment_values["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        elif connection.vendor == "postgresql":
            # A spawned interpreter otherwise reconnects to the source database,
            # not Django's disposable test database. Preserve connection options.
            source_url = urlsplit(os.environ["DATABASE_URL"])
            environment_values["DATABASE_URL"] = source_url._replace(
                path="/" + quote(str(connection.settings_dict["NAME"]), safe=""),
            ).geturl()
        environment = patch.dict(os.environ, environment_values)
        environment.start()
        self.addCleanup(environment.stop)
        self.user = get_user_model().objects.create_user("isolated-worker-owner")

    def tearDown(self):
        self.settings_override.disable()
        import shutil

        shutil.rmtree(self.private_root, ignore_errors=True)

    def test_isolated_executor_publishes_only_through_parent_fencing(self):
        job = self.create_job("test.success")

        execute_claimed_job(
            claim_next_job("worker-isolated"),
            isolated_resolver,
            timeout_seconds=5,
            isolate=True,
        )

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(job.output_name, "result.txt")
        self.assertTrue(job.output_file.storage.exists(job.output_file.name))

    def test_parent_terminates_non_write_executor_on_timeout(self):
        job = self.create_job("test.slow")

        execute_claimed_job(
            claim_next_job("worker-timeout"),
            isolated_resolver,
            timeout_seconds=0.2,
            isolate=True,
        )

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "JOB_EXECUTION_TIMEOUT")
        self.assertFalse(job.output_file)

    def test_parent_cleans_private_scratch_after_timeout_cancel_crash_and_success(self):
        fallback = self.private_root / "fallback-temp"
        fallback.mkdir()
        for mode in ("timeout", "cancel", "crash", "success"):
            with self.subTest(mode=mode):
                marker = self.private_root / f"scratch-{mode}.json"
                job = self.create_job("test.scratch")
                job.parameters = {"scratch_marker": str(marker), "scratch_mode": mode}
                job.save(update_fields=["parameters"])
                paths = []
                try:
                    with patch.dict(os.environ, {
                        "TMPDIR": str(fallback), "TEMP": str(fallback), "TMP": str(fallback),
                    }):
                        execute_claimed_job(
                            claim_next_job(f"worker-scratch-{mode}"), isolated_resolver,
                            timeout_seconds=1 if mode == "timeout" else 5, isolate=True,
                        )
                    self.assertTrue(marker.exists(), "Child must allocate scratch before termination")
                    paths = [Path(path) for path in json.loads(marker.read_text())]
                    self.assertFalse(any(path.exists() for path in paths))
                    self.assertTrue(all(
                        path.is_relative_to(self.private_root.resolve() / ".scratch/jobs")
                        for path in paths
                    ))
                    job.refresh_from_db()
                    self.assertEqual(job.status, {
                        "timeout": JobStatus.FAILED, "cancel": JobStatus.CANCELLED,
                        "crash": JobStatus.FAILED, "success": JobStatus.SUCCEEDED,
                    }[mode])
                    if mode == "success":
                        with job.output_file.open("rb") as output:
                            self.assertEqual(output.read(), b"private scratch result")
                finally:
                    # Keep a failing regression from leaking its synthetic files.
                    if marker.exists():
                        paths = [Path(path) for path in json.loads(marker.read_text())]
                    for path in paths:
                        if path.is_dir():
                            shutil.rmtree(path)
                        else:
                            path.unlink(missing_ok=True)

    def test_parent_terminates_non_write_executor_on_cancellation(self):
        job = self.create_job("test.slow")
        claimed = claim_next_job("worker-cancel")
        request_cancellation(job)

        execute_claimed_job(
            claimed,
            isolated_resolver,
            timeout_seconds=5,
            isolate=True,
        )

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.CANCELLED)
        self.assertFalse(job.output_file)

    def test_external_write_success_wins_cancellation_race(self):
        job = self.create_job("external.success", external_write=True)
        claimed = claim_next_job("worker-write-success")
        request_cancellation(job)

        execute_claimed_job(
            claimed,
            isolated_resolver,
            timeout_seconds=5,
            isolate=True,
        )

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(job.progress, 100)

    def test_external_write_timeout_requires_reconciliation(self):
        job = self.create_job("external.slow", external_write=True)

        execute_claimed_job(
            claim_next_job("worker-write-timeout"),
            isolated_resolver,
            timeout_seconds=0.2,
            isolate=True,
        )

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(job.error_code, "RECONCILIATION_REQUIRED")
        self.assertFalse(job.retryable)

    def test_containment_exit_timeout_never_publishes_or_retries_external_write(self):
        for external_write in (False, True):
            with self.subTest(external_write=external_write):
                job = self.create_job("test.success", external_write=external_write)
                with patch("jobs.process_tree.ExecutorProcessTree.wait_for_exit", return_value=False):
                    execute_claimed_job(
                        claim_next_job("worker-tree-exit-timeout"), isolated_resolver,
                        timeout_seconds=5, isolate=True,
                    )
                job.refresh_from_db()
                if external_write:
                    self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
                    self.assertFalse(job.retryable)
                else:
                    self.assertEqual(job.status, JobStatus.FAILED)
                    self.assertEqual(job.error_code, "JOB_EXECUTOR_STOP_FAILED")
                self.assertFalse(job.output_file)

    def test_nested_processes_stop_on_timeout_cancellation_crash_and_success(self):
        for mode in ("timeout", "cancel", "crash", "success"):
            with self.subTest(mode=mode):
                marker = self.private_root / f"tree-{mode}.json"
                job = self.create_job("test.nested")
                job.parameters = {"tree_marker": str(marker), "tree_mode": mode}
                job.save(update_fields=["parameters"])
                pids = []
                try:
                    execute_claimed_job(
                        claim_next_job(f"worker-tree-{mode}"), isolated_resolver,
                        timeout_seconds=2 if mode == "timeout" else 5, isolate=True,
                    )
                    self.assertTrue(marker.exists(), "Nested fixture must start before stop")
                    pids = json.loads(marker.read_text())
                    deadline = time.monotonic() + 3
                    while any(self.process_is_running(pid) for pid in pids) and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertFalse(any(self.process_is_running(pid) for pid in pids))
                    job.refresh_from_db()
                    self.assertEqual(job.status, {
                        "timeout": JobStatus.FAILED, "cancel": JobStatus.CANCELLED,
                        "crash": JobStatus.FAILED, "success": JobStatus.SUCCEEDED,
                    }[mode])
                finally:
                    if marker.exists():
                        pids = json.loads(marker.read_text())
                    for pid in pids:
                        if self.process_is_running(pid):
                            try:
                                os.kill(pid, 9)
                            except ProcessLookupError:
                                pass

    def test_worker_shutdown_stops_detached_descendants_and_preserves_write_uncertainty(self):
        for external_write in (False, True):
            with self.subTest(external_write=external_write):
                marker = self.private_root / f"shutdown-tree-{external_write}.json"
                job = self.create_job("test.nested", external_write=external_write)
                job.parameters = {"tree_marker": str(marker), "tree_mode": "shutdown"}
                job.save(update_fields=["parameters"])
                stopping = Event()
                finished = Event()
                pids = []

                def request_shutdown():
                    while not finished.wait(0.02):
                        try:
                            pids.extend(json.loads(marker.read_text()))
                        except (FileNotFoundError, json.JSONDecodeError):
                            continue
                        stopping.set()
                        return

                requester = Thread(target=request_shutdown, daemon=True)
                requester.start()
                try:
                    self.run_worker_once(job, stopping, timeout=3)
                    job.refresh_from_db()
                    self.assertTrue(stopping.is_set(), "Executor descendants must start before shutdown")
                    self.assertFalse(any(self.process_is_running(pid) for pid in pids))
                    self.assertFalse(job.output_file)
                    if external_write:
                        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
                        self.assertEqual(job.error_code, "RECONCILIATION_REQUIRED")
                        self.assertFalse(job.retryable)
                    else:
                        self.assertEqual(job.status, JobStatus.FAILED)
                        self.assertEqual(job.error_code, "JOB_WORKER_STOPPED")
                        self.assertTrue(job.retryable)
                    self.assertFalse(list((self.private_root / ".scratch/jobs").glob("*/*/*")))
                finally:
                    finished.set()
                    requester.join(timeout=5)
                    for pid in pids:
                        if self.process_is_running(pid):
                            try:
                                os.kill(pid, 9)
                            except ProcessLookupError:
                                pass

    def test_worker_shutdown_before_executor_ready_uses_shutdown_state(self):
        stopping = Event()
        process = Mock()
        process.is_alive.return_value = True
        connection = Mock()
        polls = 0

        def poll(_timeout=None):
            nonlocal polls
            polls += 1
            stopping.set()
            return polls > 1

        connection.poll.side_effect = poll
        connection.recv.return_value = {"outcome": "startup_failed", "error_type": "Interrupted"}
        child = SimpleNamespace(process=process, connection=connection, tree=None, scratch_directory=None)
        job = self.create_job("test.slow")

        with patch("jobs.worker.start_executor_process", return_value=child):
            self.run_worker_once(job, stopping)

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "JOB_WORKER_STOPPED")
        self.assertTrue(job.retryable)
        process.terminate.assert_called()
        connection.close.assert_called_once()

    def run_worker_once(self, job, stopping, timeout=5):
        from jobs.management.commands.run_job_worker import Command

        command = Command()
        command.stopping = stopping
        with (
            patch("jobs.management.commands.run_job_worker.local_job_kinds", return_value=(job.kind,)),
            patch("jobs.management.commands.run_job_worker.local_job_timeout", return_value=timeout),
            patch("jobs.management.commands.run_job_worker.resolve_job_executor", isolated_resolver),
        ):
            command.run_loop("worker-shutdown", {"once": True, "poll_interval": 0.1})

    def process_is_running(self, pid):
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                code = wintypes.DWORD()
                kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                return code.value == 259
            finally:
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.CloseHandle(handle)
        state = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return bool(state) and not state.startswith("Z")

    def test_containment_failure_stops_executor_before_it_can_spawn_children(self):
        marker = self.private_root / "tree-start-failed.json"
        job = self.create_job("test.nested")
        job.parameters = {"tree_marker": str(marker), "tree_mode": "success"}
        job.save(update_fields=["parameters"])
        started = []

        def fail_containment(process):
            started.append(process.pid)
            raise PermissionError("containment fixture")

        with patch("jobs.worker.ExecutorProcessTree", side_effect=fail_containment):
            with self.assertRaises(PermissionError):
                start_executor_process(claim_next_job("worker-containment-failure"), isolated_resolver)

        self.assertEqual(len(started), 1)
        self.assertFalse(self.process_is_running(started[0]))
        self.assertFalse(marker.exists())
        self.assertFalse(list((self.private_root / ".scratch/jobs").glob("*/*/*")))

    def test_failed_process_start_removes_parent_owned_scratch(self):
        self.create_job("test.success")
        job = claim_next_job("worker-start-failure")
        import multiprocessing

        context = multiprocessing.get_context("spawn")
        process = Mock(pid=None)
        process.start.side_effect = OSError("Process start failed")
        with (
            patch("jobs.worker.multiprocessing.get_context", return_value=context),
            patch.object(context, "Process", return_value=process),
        ):
            with self.assertRaises(OSError):
                start_executor_process(job, isolated_resolver)

        self.assertFalse(list((self.private_root / ".scratch/jobs").glob("*/*/*")))

    def test_scratch_allocation_failure_closes_open_process_pipe(self):
        self.create_job("test.success")
        job = claim_next_job("worker-scratch-allocation-failure")
        import multiprocessing

        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        self.addCleanup(parent.close)
        self.addCleanup(child.close)
        with (
            patch("jobs.worker.multiprocessing.get_context", return_value=context),
            patch.object(context, "Pipe", return_value=(parent, child)),
            patch("jobs.worker.create_execution_scratch", side_effect=OSError("Storage unavailable")),
        ):
            with self.assertRaises(OSError):
                start_executor_process(job, isolated_resolver)

        self.assertTrue(parent.closed)
        self.assertTrue(child.closed)

    def test_executor_descendants_stop_before_artifact_publication(self):
        marker = self.private_root / "tree-publication.json"
        job = self.create_job("test.nested")
        job.parameters = {"tree_marker": str(marker), "tree_mode": "success"}
        job.save(update_fields=["parameters"])
        pids = []

        def publish_after_tree_stopped(*args, **kwargs):
            pids.extend(json.loads(marker.read_text()))
            self.assertFalse(any(self.process_is_running(pid) for pid in pids))
            return real_persist_result(*args, **kwargs)

        try:
            with patch("jobs.worker.persist_result", side_effect=publish_after_tree_stopped):
                execute_claimed_job(
                    claim_next_job("worker-publication-tree"), isolated_resolver,
                    timeout_seconds=5, isolate=True,
                )
            job.refresh_from_db()
            self.assertEqual(job.status, JobStatus.SUCCEEDED)
        finally:
            if marker.exists():
                for pid in json.loads(marker.read_text()):
                    if self.process_is_running(pid):
                        try:
                            os.kill(pid, 9)
                        except ProcessLookupError:
                            pass

    def create_job(self, kind, *, external_write=False):
        job, _created = create_job(
            self.user,
            kind,
            "Isolated execution",
            {},
            SimpleUploadedFile("input.json", b"{}", content_type="application/json"),
            reconcile_on_lease_loss=external_write,
        )
        return job


class WorkerCompositionTests(SimpleTestCase):
    """Lock catalog timeout and process isolation into the production worker loop."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(PRIVATE_MEDIA_ROOT=Path(directory.name))
        override.enable()
        self.addCleanup(override.disable)

    @patch("jobs.worker.ExecutorProcessTree")
    @patch("jobs.worker.connections.close_all")
    @patch("jobs.worker.multiprocessing.get_context")
    def test_macos_and_windows_use_spawn_while_linux_keeps_fork(
        self, get_context, _close, _tree
    ):
        job = SimpleNamespace(id=uuid4(), owner_id=1, execution_token=uuid4(), kind="test.success")
        get_context.return_value.Pipe.return_value = (Mock(), Mock())
        for platform, method in (("darwin", "spawn"), ("win32", "spawn"), ("linux", "fork")):
            with self.subTest(platform=platform), patch("jobs.worker.sys.platform", platform):
                job.execution_token = uuid4()
                start_executor_process(job, isolated_resolver)
                get_context.assert_called_with(method)
                self.assertIs(
                    get_context.return_value.Process.call_args.kwargs["target"],
                    bootstrap_executor_process,
                )

    def test_spawn_bootstrap_initializes_django_before_worker_import(self):
        """A fresh spawned interpreter reaches model code only after setup."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "spawn-check.sqlite3"
            code = dedent(
                """
                import multiprocessing
                from jobs.process_bootstrap import bootstrap_executor_process

                if __name__ == "__main__":
                    context = multiprocessing.get_context("spawn")
                    parent, child = context.Pipe(duplex=False)
                    process = context.Process(
                        target=bootstrap_executor_process,
                        args=(
                            "00000000-0000-0000-0000-000000000000",
                            "doors.run_dxl",
                            ("awcenter.job_executors", "resolve_worker_executor"),
                            child,
                        ),
                    )
                    process.start()
                    child.close()
                    received = parent.poll(10)
                    envelope = parent.recv() if received else None
                    process.join(5)
                    if process.is_alive():
                        process.terminate()
                        process.join(5)
                    exit_code = process.exitcode
                    parent.close()
                    assert received, exit_code
                    assert envelope == {
                        "outcome": "unhandled",
                        "error_type": "OperationalError",
                    }, envelope
                    assert exit_code == 0, exit_code
                """
            )
            environment = os.environ.copy()
            environment.update(
                {
                    "AWCENTER_DEPLOYMENT_MODE": "development",
                    "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
                    "DEBUG": "True",
                    "DJANGO_SETTINGS_MODULE": "awcenter.settings",
                    "SECRET_KEY": "spawn-bootstrap-test-only",
                }
            )

            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=Path(__file__).resolve().parents[2],
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    @patch("jobs.worker.ExecutorProcessTree")
    @patch("jobs.worker.connections.close_all")
    @patch("jobs.worker.multiprocessing.get_context")
    @patch("jobs.worker.sys.platform", "win32")
    def test_windows_process_defers_resolver_import_until_after_bootstrap(
        self, get_context, _close_connections, _tree
    ):
        """Spawn receives import-safe strings instead of importing a resolver early."""

        context = get_context.return_value
        parent_connection = Mock()
        child_connection = Mock()
        process = Mock()
        context.Pipe.return_value = (parent_connection, child_connection)
        context.Process.return_value = process
        job = SimpleNamespace(id=uuid4(), owner_id=1, execution_token=uuid4(), kind="doors.run_dxl")

        child = start_executor_process(job, isolated_resolver)

        self.assertIs(child.process, process)
        process.start.assert_called_once_with()
        child_connection.close.assert_called_once_with()
        process_options = context.Process.call_args.kwargs
        self.assertIs(process_options["target"], bootstrap_executor_process)
        self.assertEqual(
            process_options["args"][2],
            ("jobs.tests.test_isolated_worker", "isolated_resolver"),
        )
        self.assertIs(process_options["args"][3], child_connection)

    def test_worker_applies_catalog_timeout_to_isolated_executor(self):
        from jobs.management.commands.run_job_worker import Command

        command = Command()
        command.stopping = Event()
        job = SimpleNamespace(kind="word.translate")
        with (
            patch(
                "jobs.management.commands.run_job_worker.touch_worker"
            ),
            patch(
                "jobs.management.commands.run_job_worker.claim_next_job",
                return_value=job,
            ),
            patch(
                "jobs.management.commands.run_job_worker.local_job_kinds",
                return_value=(job.kind,),
            ),
            patch(
                "jobs.management.commands.run_job_worker.local_job_timeout",
                return_value=73,
            ),
            patch(
                "jobs.management.commands.run_job_worker.execute_claimed_job"
            ) as execute,
        ):
            command.run_loop("worker-test", {"once": True, "poll_interval": 1})

        execute.assert_called_once()
        self.assertEqual(execute.call_args.kwargs["timeout_seconds"], 73)
        self.assertTrue(execute.call_args.kwargs["isolate"])

    def test_windows_worker_can_consume_local_and_doors_allowlists(self):
        from jobs.management.commands.run_job_worker import Command

        command = Command()
        command.stopping = Event()
        job = SimpleNamespace(kind="doors.run_dxl")
        with (
            patch("jobs.management.commands.run_job_worker.touch_worker"),
            patch(
                "jobs.management.commands.run_job_worker.claim_next_job",
                return_value=job,
            ) as claim,
            patch(
                "jobs.management.commands.run_job_worker.worker_job_kinds",
                return_value=("word.translate", job.kind),
            ),
            patch(
                "jobs.management.commands.run_job_worker.worker_job_timeout",
                return_value=91,
            ),
            patch(
                "jobs.management.commands.run_job_worker.execute_claimed_job"
            ) as execute,
        ):
            command.run_loop(
                "doors-worker:test",
                {"once": True, "poll_interval": 1, "include_doors": True},
            )

        self.assertEqual(claim.call_args.args[1], ("word.translate", job.kind))
        self.assertEqual(execute.call_args.kwargs["timeout_seconds"], 91)
        self.assertTrue(execute.call_args.kwargs["isolate"])

    @override_settings(DOORS_ENABLED=True)
    def test_settings_aware_worker_includes_enabled_doors_queue(self):
        from jobs.management.commands.run_job_worker import resolve_include_doors

        self.assertTrue(
            resolve_include_doors(
                {"include_doors": False, "include_doors_if_enabled": True}
            )
        )

    @override_settings(DOORS_ENABLED=False)
    def test_settings_aware_worker_keeps_disabled_doors_queue_excluded(self):
        from jobs.management.commands.run_job_worker import resolve_include_doors

        self.assertFalse(
            resolve_include_doors(
                {"include_doors": False, "include_doors_if_enabled": True}
            )
        )
