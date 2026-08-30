import tempfile
import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from jobs.contracts import JobExecutionResult
from jobs.models import JobStatus
from jobs.services import create_job, request_cancellation
from jobs.worker import claim_next_job, execute_claimed_job


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
