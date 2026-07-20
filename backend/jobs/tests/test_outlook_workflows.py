import hashlib

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from jobs.models import Job, JobStatus, WorkflowRun, WorkflowStatus
from jobs.services import set_job_state

from .base import JobTestCase
from .test_document_jobs import word_upload

WORKFLOW_URL = "/jobs/workflows/"
RECIPE = "analyze-outlook-word-attachment"
OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class OutlookWorkflowApiTests(JobTestCase):
    """Verify the Outlook-to-Word bridge and its recipe-specific contract."""

    def test_catalog_describes_dynamic_inputs_and_parameters(self):
        """Recipe metadata drives the launcher without hard-coded Word fields."""

        response = self.client.get(f"{WORKFLOW_URL}recipes/")

        recipes = {item["id"]: item for item in response.data}
        self.assertEqual(recipes[RECIPE]["input"]["accept"], [".msg"])
        self.assertEqual(recipes[RECIPE]["parameters"], [])
        self.assertEqual(
            recipes["translate-and-analyze"]["parameters"][0]["name"], "translate_type"
        )

    def test_recipe_queues_private_outlook_extraction(self):
        """A valid MSG input queues the allowlisted extraction job."""

        response = self.create_workflow()

        self.assertEqual(response.status_code, 201)
        workflow = WorkflowRun.objects.get(pk=response.data["id"])
        job = workflow.jobs.get()
        self.assertEqual(workflow.parameters, {})
        self.assertEqual(job.kind, "outlook.extract_word_attachment")

    def test_each_recipe_enforces_its_own_input_policy(self):
        """MSG and DOCX inputs cannot be sent to the wrong recipe."""

        word_response = self.client.post(
            WORKFLOW_URL,
            {"recipe": RECIPE, "file": word_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="outlook-policy-001",
        )
        msg_response = self.client.post(
            WORKFLOW_URL,
            {
                "recipe": "translate-and-analyze",
                "translate_type": "tr2en",
                "file": outlook_upload(),
            },
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="outlook-policy-002",
        )

        self.assertEqual(word_response.status_code, 400)
        self.assertEqual(msg_response.status_code, 400)
        self.assertEqual(WorkflowRun.objects.count(), 0)

    def test_extracted_document_advances_to_explainable_analysis(self):
        """A verified extraction output becomes the analysis input automatically."""

        workflow = WorkflowRun.objects.get(pk=self.create_workflow().data["id"])
        source = workflow.jobs.get()
        payload = word_upload().read()
        source.output_name = "attachment.docx"
        source.output_sha256 = hashlib.sha256(payload).hexdigest()
        source.output_file.save(source.output_name, ContentFile(payload), save=False)

        set_job_state(source, JobStatus.SUCCEEDED, 100, "Word attachment extracted.")

        workflow.refresh_from_db()
        target = workflow.jobs.get(workflow_step=2)
        self.assertEqual(workflow.status, WorkflowStatus.QUEUED)
        self.assertEqual(target.kind, "word.analyze")
        self.assertEqual(target.source_job, source)
        self.assertEqual(target.input_sha256, source.output_sha256)

    def create_workflow(self):
        """Post a minimally signature-valid Outlook workflow request."""

        return self.client.post(
            WORKFLOW_URL,
            {"recipe": RECIPE, "file": outlook_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="outlook-workflow-001",
        )


def outlook_upload(name="message.msg"):
    """Return a minimally signature-valid Outlook upload for API tests."""

    return SimpleUploadedFile(
        name, OLE_SIGNATURE + b"outlook-message", content_type="application/vnd.ms-outlook"
    )
