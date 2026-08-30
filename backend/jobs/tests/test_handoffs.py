import hashlib

from django.core.files.base import ContentFile

from jobs.models import Job, JobStatus
from jobs.services import create_job, set_job_state

from .base import JobTestCase
from .test_document_jobs import word_upload


HANDOFF_URL = "analyze-translated-document"


class JobHandoffApiTests(JobTestCase):
    """Keep feature-owned workflow transitions off the generic Job API."""

    def test_completed_output_does_not_advertise_generic_handoffs(self):
        """Job detail remains status-only even for a compatible private output."""

        source = self.completed_translation()

        response = self.client.get(f"/api/jobs/{source.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("handoffs", response.data)
        self.assertNotIn("can_retry", response.data)

    def test_generic_handoff_endpoint_is_not_published(self):
        """A caller cannot select a target executor through the Job API."""

        source = self.completed_translation()

        response = self.client.post(
            f"/api/jobs/{source.id}/handoffs/{HANDOFF_URL}/"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Job.objects.count(), 1)

    def test_generic_retry_endpoint_is_not_published(self):
        """A caller cannot duplicate even a terminal downstream operation."""

        source = self.completed_translation()
        set_job_state(source, JobStatus.FAILED, 10, "Failed.", "TEST_FAILURE")

        response = self.client.post(f"/api/jobs/{source.id}/retry/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Job.objects.count(), 1)

    def completed_translation(self):
        """Create a succeeded translation with a fingerprinted private output."""

        source, _created = create_job(
            self.user,
            "word.translate",
            "Translate document",
            {"translate_type": "tr2en"},
            word_upload(),
        )
        payload = word_upload().read()
        source.output_name = "[TR-EN] document.docx"
        source.output_sha256 = hashlib.sha256(payload).hexdigest()
        source.output_file.save(source.output_name, ContentFile(payload), save=False)
        set_job_state(source, JobStatus.SUCCEEDED, 100, "Word translation completed.")
        return source
