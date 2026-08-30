import os
import tempfile
import shutil
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from awcenter.job_executors import resolve_job_executor
from jobs.contracts import (
    JobCancelled,
    JobExecutionFailure,
    JobExecutionResult,
    JobExecutionUncertain,
    JobLeaseLost,
)
from jobs.execution import (
    ExecutionHeartbeat,
    ExecutionLease,
    bind_execution,
    renew_execution_lease,
    update_progress,
)
from jobs.models import Job, JobStatus, WorkerHeartbeat
from jobs.services import create_job, request_cancellation, set_job_state
from jobs.worker import claim_next_job, execute_claimed_job, recover_expired_jobs
from jobs.artifacts import materialize_job_input, stage_job_output as real_stage_job_output
from jobs.retention import cleanup_orphan_artifacts
from media_tools.job_executor import run_cancellable_ffmpeg
from media_tools.services import MediaParameters
from .base import JobTestCase


class JobWorkerTests(JobTestCase):
    """Verify worker leasing, artifacts, cancellation, and recovery."""

    def test_worker_claims_and_completes_job(self):
        """A claimed executor result becomes an owned downloadable artifact."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        output_path = self.output_file(b"converted")
        result = JobExecutionResult(output_path, "converted.png")

        claimed = claim_next_job("worker-1")
        execute_claimed_job(claimed, lambda _kind: lambda _job: result)

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.events.last().status, JobStatus.SUCCEEDED)
        self.assertTrue(job.output_file.storage.exists(job.output_file.name))
        self.assertIsNone(job.execution_token)
        self.assertEqual(job.worker_id, "")

    @override_settings(JOB_EXECUTION_TIMEOUT_SECONDS=60, JOB_LEASE_SECONDS=60)
    def test_cleanup_removes_old_staging_and_unreferenced_final_artifacts(self):
        staging = self.media_directory / "private/.staging/jobs/1/job/stale.bin.part"
        orphan = self.media_directory / "private/jobs/1/orphan/output.bin"
        staging.parent.mkdir(parents=True)
        orphan.parent.mkdir(parents=True)
        staging.write_bytes(b"stale")
        orphan.write_bytes(b"orphan")
        old = (timezone.now() - timedelta(minutes=5)).timestamp()
        os.utime(staging, (old, old))
        os.utime(orphan, (old, old))

        staging_count, orphan_count = cleanup_orphan_artifacts()

        self.assertEqual((staging_count, orphan_count), (1, 1))
        self.assertFalse(staging.exists())
        self.assertFalse(orphan.exists())

    @override_settings(FFMPEG_EXECUTABLE="ffmpeg", JOB_EXECUTION_TIMEOUT_SECONDS=30)
    def test_real_ffmpeg_executor_completes_when_available(self):
        """Exercise the complete durable media adapter with the installed FFmpeg."""

        if not shutil.which("ffmpeg"):
            self.skipTest("FFmpeg is not installed in this test environment.")
        job, _ = create_job(
            self.user, "media.convert", "Convert", {"output_extension": "png"},
            self.valid_jpeg_upload(),
        )

        claimed = claim_next_job("worker-real")
        execute_claimed_job(claimed, resolve_job_executor)

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertGreater(job.output_file.size, 0)

    def test_composition_catalog_rejects_unknown_job_kind(self):
        """Persisted kind data cannot select an arbitrary import or callback."""

        job, _ = create_job(self.user, "unknown.kind", "Unknown", {}, self.image_upload())

        execute_claimed_job(claim_next_job("worker-allowlist"), resolve_job_executor)

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "JOB_KIND_UNSUPPORTED")

    def test_uncertain_external_write_requires_manual_reconciliation(self):
        """Ambiguous provider outcomes are terminal and never auto-retry."""

        job, _ = create_job(self.user, "media.convert", "Write", {}, self.image_upload())

        def uncertain(_job):
            raise JobExecutionUncertain()

        execute_claimed_job(
            claim_next_job("worker-uncertain"),
            lambda _kind: uncertain,
        )

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(job.error_code, "RECONCILIATION_REQUIRED")
        self.assertFalse(job.retryable)

    def test_running_job_uses_cooperative_cancel_state(self):
        """Running cancellation records intent for the executor heartbeat."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        claimed = claim_next_job("worker-cancel")

        updated = request_cancellation(job)

        self.assertEqual(updated.status, JobStatus.CANCEL_REQUESTED)
        self.assertIsNotNone(updated.cancel_requested_at)
        self.assertEqual(updated.execution_token, claimed.execution_token)

    def test_expired_worker_lease_requeues_attempt(self):
        """An interrupted worker lease is recoverable without losing the job."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        claim_next_job("worker-expired")
        Job.objects.filter(pk=job.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )

        recover_expired_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(job.attempt, 2)
        self.assertIsNone(job.execution_token)
        self.assertEqual(job.worker_id, "")

    def test_each_recovered_claim_receives_a_new_execution_token(self):
        """A recovered job cannot reuse the fencing identity of its stale worker."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        first_claim = claim_next_job("worker-old")
        Job.objects.filter(pk=job.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )

        second_claim = claim_next_job("worker-new")

        self.assertNotEqual(first_claim.execution_token, second_claim.execution_token)
        self.assertEqual(second_claim.worker_id, "worker-new")

    def test_stale_claim_cannot_publish_progress_after_recovery(self):
        """Progress CAS rejects the token from a replaced execution claim."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        stale_claim = claim_next_job("worker-old")
        Job.objects.filter(pk=job.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        current_claim = claim_next_job("worker-new")

        with bind_execution(stale_claim):
            with self.assertRaises(JobLeaseLost):
                update_progress(job.id, 80, "Stale worker progress.")

        job.refresh_from_db()
        self.assertEqual(job.execution_token, current_claim.execution_token)
        self.assertEqual(job.progress, 0)
        self.assertNotEqual(job.message, "Stale worker progress.")

    def test_stale_executor_cannot_publish_result_after_recovery(self):
        """Terminal CAS discards output from an executor whose lease was replaced."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        stale_claim = claim_next_job("worker-old")
        output_path = self.output_file(b"stale result")
        replacement = {}

        def replace_claim(staged_job, filename, source):
            artifact = real_stage_job_output(staged_job, filename, source)
            Job.objects.filter(pk=job.id).update(
                lease_expires_at=timezone.now() - timedelta(seconds=1)
            )
            replacement["claim"] = claim_next_job("worker-new")
            return artifact

        result = JobExecutionResult(output_path, "stale.png")
        with patch("jobs.worker.stage_job_output", side_effect=replace_claim):
            execute_claimed_job(stale_claim, lambda _kind: lambda _job: result)

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.RUNNING)
        self.assertEqual(job.execution_token, replacement["claim"].execution_token)
        self.assertFalse(job.output_file)
        self.assertFalse(list(Path(job.input_file.path).parent.glob("output*")))

    def test_external_write_lease_loss_requires_reconciliation(self):
        """An ambiguous write is never auto-requeued after its claim expires."""

        job, _ = create_job(
            self.user,
            "teamcenter.set_properties",
            "External write",
            {},
            self.image_upload(),
            reconcile_on_lease_loss=True,
        )
        claim_next_job("worker-write")
        Job.objects.filter(pk=job.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )

        recover_expired_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(job.error_code, "RECONCILIATION_REQUIRED")
        self.assertFalse(job.retryable)

    def test_external_write_cancel_recovery_requires_reconciliation(self):
        """A lost worker cannot prove a dispatched write was safely cancelled."""

        job, _ = create_job(
            self.user,
            "teamcenter.set_properties",
            "External write",
            {},
            self.image_upload(),
            reconcile_on_lease_loss=True,
        )
        claim_next_job("worker-write-cancel")
        request_cancellation(job)
        Job.objects.filter(pk=job.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )

        recover_expired_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(job.error_code, "RECONCILIATION_REQUIRED")
        self.assertFalse(job.retryable)

    def test_heartbeat_renews_claim_without_executor_progress(self):
        """The independent heartbeat path extends a live claim and publishes liveness."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        claimed = claim_next_job("worker-heartbeat")
        original_deadline = claimed.lease_expires_at
        renewal_seconds = max(
            120, int((original_deadline - timezone.now()).total_seconds()) + 60
        )

        with override_settings(JOB_LEASE_SECONDS=renewal_seconds):
            self.assertTrue(renew_execution_lease(ExecutionLease.from_job(claimed)))

        job.refresh_from_db()
        heartbeat = WorkerHeartbeat.objects.get(worker_id="worker-heartbeat")
        self.assertGreater(job.lease_expires_at, original_deadline)
        self.assertEqual(heartbeat.current_job_id, job.id)

    def test_heartbeat_cannot_resurrect_an_expired_claim(self):
        """A delayed heartbeat loses the CAS race once its lease is expired."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        claimed = claim_next_job("worker-late")
        expired_at = timezone.now() - timedelta(seconds=1)
        Job.objects.filter(pk=job.id).update(lease_expires_at=expired_at)

        self.assertFalse(renew_execution_lease(ExecutionLease.from_job(claimed)))

        job.refresh_from_db()
        self.assertEqual(job.lease_expires_at, expired_at)

    @patch("jobs.execution.heartbeat_interval", return_value=0.01)
    @patch("jobs.execution.renew_execution_lease", side_effect=[True, True, False])
    def test_execution_heartbeat_renews_on_its_own_thread(self, renew, _interval):
        """A quiet executor does not need to call progress to keep its claim alive."""

        lease = ExecutionLease("job-id", "worker-id", "execution-token")
        heartbeat = ExecutionHeartbeat(lease)

        heartbeat.start()
        heartbeat._thread.join(timeout=1)
        heartbeat.stop()

        self.assertFalse(heartbeat._thread.is_alive())
        self.assertEqual(renew.call_count, 3)

    def test_job_deletion_removes_private_artifacts(self):
        """Retention deletion cannot leave uploaded input files behind."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        storage = job.input_file.storage
        artifact_name = job.input_file.name

        job.delete()

        self.assertFalse(storage.exists(artifact_name))

    def test_retention_cleanup_deletes_terminal_job_and_artifacts(self):
        """Retention cleanup removes both database history and private files."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        storage = job.input_file.storage
        artifact_name = job.input_file.name
        set_job_state(job, JobStatus.FAILED, 10, "Failed", "TEST_FAILURE")
        job.completed_at = timezone.now() - timedelta(days=2)
        job.save(update_fields=["completed_at"])

        call_command("cleanup_jobs", days=1)

        self.assertFalse(storage.exists(artifact_name))
        self.assertFalse(type(job).objects.filter(pk=job.pk).exists())

    def test_invalid_retention_never_partially_deletes_expired_previews(self):
        """Retention validation happens before any private artifact is deleted."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        job.status = JobStatus.AWAITING_CONFIRMATION
        job.confirmation_expires_at = timezone.now() - timedelta(seconds=1)
        job.save(update_fields=["status", "confirmation_expires_at"])

        with self.assertRaises(ValueError):
            call_command("cleanup_jobs", days=0)

        self.assertTrue(Job.objects.filter(pk=job.id).exists())

    def test_worker_health_command_rejects_stale_heartbeats(self):
        """Container health follows durable heartbeats instead of process presence alone."""

        create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        claim_next_job("worker-health")
        worker_id_file = self.media_directory / "worker.id"
        worker_id_file.write_text("worker-health", encoding="utf-8")
        call_command("check_job_worker_health", worker_id_file=str(worker_id_file))
        WorkerHeartbeat.objects.filter(worker_id="worker-health").update(
            heartbeat_at=timezone.now() - timedelta(minutes=1)
        )

        with self.assertRaises(CommandError):
            call_command("check_job_worker_health", worker_id_file=str(worker_id_file))

    def test_worker_rejects_corrupted_stored_input(self):
        """Artifact integrity is rechecked before an external process starts."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        job.input_sha256 = "0" * 64
        job.save()

        with self.assertRaises(JobExecutionFailure) as raised:
            materialize_job_input(job)

        self.assertFalse(raised.exception.retryable)

    @patch("media_tools.job_executor.stop_process")
    @patch("media_tools.job_executor.wait_for_process")
    @patch("media_tools.job_executor.cancellation_requested", return_value=True)
    @patch("media_tools.job_executor.subprocess.Popen")
    def test_media_process_honors_cancellation(self, popen_mock, _cancelled, _wait, stop_mock):
        """A running FFmpeg child is terminated after cancellation is observed."""

        process = popen_mock.return_value
        process.poll.return_value = None

        with self.assertRaises(JobCancelled):
            run_cancellable_ffmpeg(
                "00000000-0000-0000-0000-000000000001",
                Path("input.jpg"),
                Path("output.png"),
                MediaParameters("png"),
            )

        stop_mock.assert_called_once_with(process)

    @patch("media_tools.job_executor.stop_process")
    @patch("media_tools.job_executor.wait_for_process")
    @patch("media_tools.job_executor.cancellation_requested", side_effect=JobLeaseLost())
    @patch("media_tools.job_executor.subprocess.Popen")
    def test_media_process_stops_when_its_execution_claim_is_lost(
        self, popen_mock, _lease, _wait, stop_mock
    ):
        """A fenced FFmpeg adapter cannot leave an orphan child process running."""

        process = popen_mock.return_value
        process.poll.return_value = None

        with self.assertRaises(JobLeaseLost):
            run_cancellable_ffmpeg(
                "00000000-0000-0000-0000-000000000001",
                Path("input.jpg"),
                Path("output.png"),
                MediaParameters("png"),
            )

        stop_mock.assert_called_once_with(process)

    def output_file(self, content):
        """Create a worker-owned temporary executor result."""

        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        handle.write(content)
        handle.close()
        return Path(handle.name)

    def valid_jpeg_upload(self):
        """Create a decoder-valid image for the real FFmpeg smoke test."""

        buffer = BytesIO()
        Image.new("RGB", (16, 16), color="navy").save(buffer, format="JPEG")
        return SimpleUploadedFile("input.jpg", buffer.getvalue(), content_type="image/jpeg")
