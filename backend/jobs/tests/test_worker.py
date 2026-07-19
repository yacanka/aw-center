import tempfile
import shutil
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from jobs.contracts import JobCancelled, JobExecutionFailure, JobExecutionResult
from jobs.models import JobStatus
from jobs.services import create_job, request_cancellation, set_job_state
from jobs.worker import claim_next_job, execute_claimed_job, recover_expired_jobs
from jobs.artifacts import materialize_job_input
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

        with patch("jobs.worker.get_executor", return_value=lambda _job: result):
            claimed = claim_next_job("worker-1")
            execute_claimed_job(claimed)

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.events.last().status, JobStatus.SUCCEEDED)
        self.assertTrue(job.output_file.storage.exists(job.output_file.name))

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
        execute_claimed_job(claimed)

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertGreater(job.output_file.size, 0)

    def test_running_job_uses_cooperative_cancel_state(self):
        """Running cancellation records intent for the executor heartbeat."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        job.status = JobStatus.RUNNING
        job.save()

        updated = request_cancellation(job)

        self.assertEqual(updated.status, JobStatus.CANCEL_REQUESTED)
        self.assertIsNotNone(updated.cancel_requested_at)

    def test_expired_worker_lease_requeues_attempt(self):
        """An interrupted worker lease is recoverable without losing the job."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        job.status = JobStatus.RUNNING
        job.lease_expires_at = timezone.now() - timedelta(seconds=1)
        job.save()

        recover_expired_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(job.attempt, 2)

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
