import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from jobs.contracts import JobExecutionResult
from jobs.models import JobStatus
from jobs.services import create_job, request_cancellation
from jobs.process_bootstrap import bootstrap_executor_process
from jobs.worker import claim_next_job, execute_claimed_job, start_executor_process


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


def isolated_resolver(kind):
    """Resolve only test kinds without accepting a dotted path from job data."""

    if kind.endswith(".slow"):
        return isolated_slow_executor
    return isolated_success_executor


class IsolatedWorkerTests(TransactionTestCase):
    """Exercise the production parent/child execution boundary against durable state."""

    def setUp(self):
        self.private_root = Path(tempfile.mkdtemp())
        self.settings_override = override_settings(PRIVATE_MEDIA_ROOT=self.private_root)
        self.settings_override.enable()
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

    @patch("jobs.worker.connections.close_all")
    @patch("jobs.worker.multiprocessing.get_context")
    def test_macos_and_windows_use_spawn_while_linux_keeps_fork(self, get_context, _close):
        job = SimpleNamespace(id="12345678-job", kind="test.success")
        get_context.return_value.Pipe.return_value = (Mock(), Mock())
        for platform, method in (("darwin", "spawn"), ("win32", "spawn"), ("linux", "fork")):
            with self.subTest(platform=platform), patch("jobs.worker.sys.platform", platform):
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

    @patch("jobs.worker.connections.close_all")
    @patch("jobs.worker.multiprocessing.get_context")
    @patch("jobs.worker.sys.platform", "win32")
    def test_windows_process_defers_resolver_import_until_after_bootstrap(
        self, get_context, _close_connections
    ):
        """Spawn receives import-safe strings instead of importing a resolver early."""

        context = get_context.return_value
        parent_connection = Mock()
        child_connection = Mock()
        process = Mock()
        context.Pipe.return_value = (parent_connection, child_connection)
        context.Process.return_value = process
        job = SimpleNamespace(id="12345678-job", kind="doors.run_dxl")

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
