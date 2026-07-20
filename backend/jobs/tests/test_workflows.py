import hashlib

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from jobs.models import Job, JobStatus, WorkflowRun, WorkflowStatus
from jobs.services import set_job_state

from .base import JobTestCase
from .test_document_jobs import word_upload

WORKFLOW_URL = "/jobs/workflows/"
RECIPE = "translate-and-analyze"


class WorkflowApiTests(JobTestCase):
    """Verify secure, durable, and explainable multi-step workflows."""

    def test_catalog_and_runs_require_authentication(self):
        """Workflow capabilities and owner data are unavailable anonymously."""

        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(f"{WORKFLOW_URL}recipes/").status_code, 401)
        self.assertEqual(self.client.get(WORKFLOW_URL).status_code, 401)

    def test_creation_queues_first_step_with_safe_metadata(self):
        """A supported recipe creates an owned run and its first durable job."""

        response = self.create_workflow()

        self.assertEqual(response.status_code, 201)
        workflow = WorkflowRun.objects.get(pk=response.data["id"])
        job = workflow.jobs.get()
        self.assertEqual(job.kind, "word.translate")
        self.assertEqual(job.workflow_step, 1)
        self.assertEqual(workflow.parameters, {"translate_type": "tr2en"})
        self.assertNotIn("input_sha256", response.data)

    def test_invalid_direction_is_rejected_before_workflow_persistence(self):
        """Unsupported recipe parameters cannot consume storage or worker capacity."""

        response = self.create_workflow(translation="tr2xx")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(WorkflowRun.objects.count(), 0)
        self.assertEqual(Job.objects.count(), 0)

    def test_workflow_creation_is_idempotent_and_conflict_safe(self):
        """One request key cannot create duplicates or alias different parameters."""

        payload = word_upload().read()
        first = self.create_workflow(payload=payload, key="workflow-request-123")
        replay = self.create_workflow(payload=payload, key="workflow-request-123")
        conflict = self.create_workflow(
            payload=payload, key="workflow-request-123", translation="en2tr"
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(WorkflowRun.objects.count(), 1)
        self.assertEqual(Job.objects.count(), 1)

    def test_succeeded_step_queues_verified_handoff_and_finalizes_run(self):
        """A source output advances automatically and the final job completes the run."""

        workflow = self.workflow()
        source = workflow.jobs.get()
        self.complete_job(source, word_upload().read(), "translated.docx")

        workflow.refresh_from_db()
        target = workflow.jobs.get(workflow_step=2)
        self.assertEqual(workflow.current_step, 2)
        self.assertEqual(target.kind, "word.analyze")
        self.assertEqual(target.source_job, source)
        self.assertEqual(target.input_sha256, source.output_sha256)

        self.complete_job(target, b'{"safe": true}', "analysis.json")
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, WorkflowStatus.SUCCEEDED)
        self.assertIsNotNone(workflow.completed_at)
        self.assertTrue(workflow.events.filter(status=WorkflowStatus.SUCCEEDED).exists())

    def test_step_failure_is_explained_and_retry_resumes_same_sequence(self):
        """A retryable failed step pauses the run and a job retry resumes it."""

        workflow = self.workflow()
        source = workflow.jobs.get()
        set_job_state(source, JobStatus.FAILED, 25, "Translation model unavailable.", "MODEL_DOWN")

        workflow.refresh_from_db()
        self.assertEqual(workflow.status, WorkflowStatus.FAILED)
        self.assertEqual(workflow.error_code, "MODEL_DOWN")

        response = self.client.post(f"/jobs/{source.id}/retry/")
        workflow.refresh_from_db()
        retry = Job.objects.get(pk=response.data["id"])
        self.assertEqual(workflow.status, WorkflowStatus.QUEUED)
        self.assertEqual(retry.workflow_run, workflow)
        self.assertEqual(retry.workflow_step, 1)

    def test_tampered_output_fails_workflow_without_rewriting_job_success(self):
        """An integrity failure blocks advancement but preserves source truth."""

        workflow = self.workflow()
        source = workflow.jobs.get()
        source.output_name = "translated.docx"
        source.output_sha256 = "0" * 64
        source.output_file.save(source.output_name, ContentFile(word_upload().read()), save=False)

        set_job_state(source, JobStatus.SUCCEEDED, 100, "Translation completed.")

        workflow.refresh_from_db()
        source.refresh_from_db()
        self.assertEqual(source.status, JobStatus.SUCCEEDED)
        self.assertEqual(workflow.status, WorkflowStatus.FAILED)
        self.assertEqual(workflow.error_code, "WORKFLOW_ADVANCE_FAILED")
        self.assertEqual(workflow.jobs.count(), 1)

    def test_cancellation_and_detail_are_owner_scoped(self):
        """Only the owner can inspect or cancel an active workflow."""

        workflow = self.workflow()
        self.client.force_authenticate(self.other_user)

        self.assertEqual(self.client.get(f"{WORKFLOW_URL}{workflow.id}/").status_code, 404)
        self.assertEqual(
            self.client.post(f"{WORKFLOW_URL}{workflow.id}/cancel/").status_code, 404
        )
        self.client.force_authenticate(self.user)
        response = self.client.post(f"{WORKFLOW_URL}{workflow.id}/cancel/")
        self.assertEqual(response.data["status"], WorkflowStatus.CANCELLED)

    def test_running_cancellation_waits_for_worker_confirmation(self):
        """A running workflow is not reported terminal before its worker stops."""

        workflow = self.workflow()
        source = workflow.jobs.get()
        set_job_state(source, JobStatus.RUNNING, 10, "Translation started.")

        response = self.client.post(f"{WORKFLOW_URL}{workflow.id}/cancel/")
        replay = self.client.post(f"{WORKFLOW_URL}{workflow.id}/cancel/")
        source.refresh_from_db()
        self.assertEqual(response.data["status"], WorkflowStatus.CANCEL_REQUESTED)
        self.assertEqual(replay.data["status"], WorkflowStatus.CANCEL_REQUESTED)
        self.assertEqual(source.status, JobStatus.CANCEL_REQUESTED)

        set_job_state(source, JobStatus.CANCELLED, 10, "Job cancelled.", "JOB_CANCELLED")
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, WorkflowStatus.CANCELLED)

    def workflow(self):
        """Create and return one representative workflow run."""

        return WorkflowRun.objects.get(pk=self.create_workflow().data["id"])

    def create_workflow(self, payload=None, key="workflow-request-001", translation="tr2en"):
        """Post a minimally valid Word workflow request."""

        content = payload if payload is not None else word_upload().read()
        upload = SimpleUploadedFile(
            "document.docx", content,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        return self.client.post(
            WORKFLOW_URL,
            {"recipe": RECIPE, "translate_type": translation, "file": upload},
            format="multipart", HTTP_IDEMPOTENCY_KEY=key,
        )

    def complete_job(self, job, payload, filename):
        """Persist one deterministic output and trigger workflow synchronization."""

        job.output_name = filename
        job.output_sha256 = hashlib.sha256(payload).hexdigest()
        job.output_file.save(filename, ContentFile(payload), save=False)
        set_job_state(job, JobStatus.SUCCEEDED, 100, "Step completed.")
