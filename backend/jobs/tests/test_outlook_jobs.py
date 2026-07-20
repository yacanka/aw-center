from unittest.mock import patch

from jobs.models import Job, JobStatus
from jobs.services import create_job
from jobs.worker import claim_next_job, execute_claimed_job

from .base import JobTestCase
from .test_document_jobs import word_upload
from .test_outlook_workflows import outlook_upload


class FakeAttachment:
    """Represent the extract-msg attachment fields used by the executor."""

    def __init__(self, name, data):
        self.longFilename = name
        self.shortFilename = None
        self.data = data


class FakeMessage:
    """Represent a closeable Outlook message for deterministic worker tests."""

    def __init__(self, attachments):
        self.attachments = attachments
        self.closed = False

    def close(self):
        """Record resource cleanup."""

        self.closed = True


class OutlookJobTests(JobTestCase):
    """Verify durable, sanitized Outlook attachment extraction."""

    def test_job_api_enqueues_extraction_without_browser_cache(self):
        """The standalone bridge endpoint persists a private durable job."""

        response = self.client.post(
            "/outlook/jobs/extract-word-attachment/",
            {"file": outlook_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Job.objects.get(pk=response.data["id"]).kind, "outlook.extract_word_attachment")

    @patch("outlook.job_executor.open_message")
    def test_executor_extracts_one_valid_docx_attachment(self, open_message_mock):
        """One safe DOCX attachment becomes a fingerprinted private output."""

        message = FakeMessage([FakeAttachment("evidence.docx", word_upload().read())])
        open_message_mock.return_value = message
        job = self.execute_job()

        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(job.output_name, "evidence.docx")
        self.assertEqual(job.result_summary["attachment_name"], "evidence.docx")
        self.assertGreater(job.output_file.size, 0)
        self.assertTrue(message.closed)

    @patch("outlook.job_executor.open_message")
    def test_executor_rejects_ambiguous_word_attachments(self, open_message_mock):
        """Multiple Word documents require explicit user disambiguation."""

        content = word_upload().read()
        open_message_mock.return_value = FakeMessage(
            [FakeAttachment("one.docx", content), FakeAttachment("two.docx", content)]
        )

        job = self.execute_job()

        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "OUTLOOK_WORD_ATTACHMENT_AMBIGUOUS")
        self.assertFalse(job.retryable)

    @patch("outlook.job_executor.open_message")
    def test_executor_rejects_disguised_word_attachment(self, open_message_mock):
        """A DOCX filename cannot bypass OOXML content validation."""

        open_message_mock.return_value = FakeMessage(
            [FakeAttachment("evidence.docx", b"not-an-office-document")]
        )

        job = self.execute_job()

        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "OUTLOOK_ATTACHMENT_UNSAFE")
        self.assertNotIn("zip", job.message.lower())

    def execute_job(self):
        """Create, claim, execute, and reload one representative extraction job."""

        job, _ = create_job(
            self.user,
            "outlook.extract_word_attachment",
            "Extract attachment",
            {},
            outlook_upload(),
        )
        execute_claimed_job(claim_next_job("outlook-worker"))
        job.refresh_from_db()
        return job
