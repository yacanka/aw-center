import hashlib

from django.core.files.base import ContentFile

from jobs.models import Job, JobStatus, WorkerHeartbeat
from jobs.services import create_job, set_job_state
from .base import JobTestCase


class JobApiTests(JobTestCase):
    """Verify ownership, idempotency, cancellation, and downloads."""

    def test_media_job_is_durable_and_idempotent(self):
        """Repeated safe keys return the same persisted job."""

        headers = {"HTTP_IDEMPOTENCY_KEY": "media-request-123"}
        payload = {"file": self.image_upload(), "output_extension": "png"}
        first = self.client.post("/api/tools/media/jobs/", payload, format="multipart", **headers)
        replay = self.client.post(
            "/api/tools/media/jobs/",
            {"file": self.image_upload(), "output_extension": "png"},
            format="multipart",
            **headers,
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(replay["Idempotency-Replayed"], "true")

    def test_job_list_never_exposes_another_users_job(self):
        """Job Center results are owner-scoped by default."""

        create_job(self.other_user, "media.convert", "Private", {}, self.image_upload())

        response = self.client.get("/api/jobs/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_idempotency_key_rejects_different_input(self):
        """One idempotency key cannot silently alias a different operation."""

        headers = {"HTTP_IDEMPOTENCY_KEY": "media-request-456"}
        self.client.post(
            "/api/tools/media/jobs/",
            {"file": self.image_upload(), "output_extension": "png"},
            format="multipart",
            **headers,
        )

        response = self.client.post(
            "/api/tools/media/jobs/",
            {"file": self.image_upload("other.jpg"), "output_extension": "webp"},
            format="multipart",
            **headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "IDEMPOTENCY_CONFLICT")

    def test_queued_job_can_be_cancelled_without_generic_retry_api(self):
        """Feature endpoints own creation; Job API cannot duplicate an operation."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        cancelled = self.client.post(f"/api/jobs/{job.id}/cancel/")
        retried = self.client.post(f"/api/jobs/{job.id}/retry/")

        self.assertEqual(cancelled.data["status"], JobStatus.CANCELLED)
        self.assertEqual(retried.status_code, 404)
        self.assertEqual(Job.objects.count(), 1)

    def test_job_serializer_does_not_advertise_retry_or_handoff_controls(self):
        """The status surface cannot expose removed generic mutation controls."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        self.client.post(f"/api/jobs/{job.id}/cancel/")

        detail = self.client.get(f"/api/jobs/{job.id}/")

        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("can_retry", detail.data)
        self.assertNotIn("retryable", detail.data)
        self.assertNotIn("handoffs", detail.data)

    def test_output_download_requires_ownership(self):
        """A completed artifact cannot be downloaded by another user."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        payload = b"result"
        job.output_file.save("converted.png", ContentFile(payload), save=False)
        job.output_name = "converted.png"
        job.output_sha256 = hashlib.sha256(payload).hexdigest()
        set_job_state(job, JobStatus.SUCCEEDED, 100, "Done")
        self.client.force_authenticate(self.other_user)

        response = self.client.get(f"/api/jobs/{job.id}/download/")

        self.assertEqual(response.status_code, 404)

    def test_output_download_rejects_tampered_artifact(self):
        """Stored content must still match the worker-published digest."""

        job, _ = create_job(self.user, "media.convert", "Convert", {}, self.image_upload())
        job.output_file.save("converted.png", ContentFile(b"tampered"), save=False)
        job.output_name = "converted.png"
        job.output_sha256 = hashlib.sha256(b"expected").hexdigest()
        set_job_state(job, JobStatus.SUCCEEDED, 100, "Done")

        response = self.client.get(f"/api/jobs/{job.id}/download/")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "JOB_OUTPUT_INTEGRITY_FAILED")

    def test_input_digest_is_streamed_and_persisted(self):
        """Queued inputs retain a SHA-256 integrity fingerprint."""

        upload = self.image_upload()
        expected = hashlib.sha256(upload.read()).hexdigest()
        upload.seek(0)

        job, _ = create_job(self.user, "media.convert", "Convert", {}, upload)

        self.assertEqual(job.input_sha256, expected)
        self.assertNotIn(upload.name, job.input_file.name)

    def test_system_status_reports_durable_worker_heartbeat(self):
        """Job Center can distinguish safe queueing from worker availability."""

        WorkerHeartbeat.objects.create(worker_id="worker-1")

        response = self.client.get("/api/jobs/system/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["active_workers"], 1)
