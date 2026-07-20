import hashlib

from django.core.files.base import ContentFile

from jobs.models import Job, JobStatus
from jobs.services import create_job, set_job_state
from word.analysis_contracts import ANALYSIS_CHECKS

from .base import JobTestCase
from .test_document_jobs import word_upload


HANDOFF_URL = "analyze-translated-document"


class JobHandoffApiTests(JobTestCase):
    """Verify secure, idempotent provenance between compatible jobs."""

    def test_completed_translation_exposes_explainable_next_action(self):
        """Only a verified compatible output advertises its target workflow."""

        source = self.completed_translation()

        response = self.client.get(f"/jobs/{source.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["handoffs"][0]["id"], HANDOFF_URL)
        self.assertEqual(response.data["handoffs"][0]["target_kind"], "word.analyze")

    def test_handoff_reuses_output_with_integrity_and_provenance(self):
        """The target input matches the source output and records both links."""

        source = self.completed_translation()

        response = self.client.post(f"/jobs/{source.id}/handoffs/{HANDOFF_URL}/")

        self.assertEqual(response.status_code, 201)
        target = Job.objects.get(pk=response.data["id"])
        self.assertEqual(target.kind, "word.analyze")
        self.assertEqual(target.source_job, source)
        self.assertEqual(target.parameters["check_ids"], list(ANALYSIS_CHECKS))
        self.assertEqual(target.input_sha256, source.output_sha256)
        self.assertTrue(source.events.filter(details__target_job_id=str(target.id)).exists())
        self.assertTrue(target.events.filter(details__source_job_id=str(source.id)).exists())

    def test_repeated_handoff_returns_the_original_target(self):
        """Repeated clicks cannot enqueue duplicate downstream work."""

        source = self.completed_translation()
        first = self.client.post(f"/jobs/{source.id}/handoffs/{HANDOFF_URL}/")
        replay = self.client.post(f"/jobs/{source.id}/handoffs/{HANDOFF_URL}/")

        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["id"], first.data["id"])
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(Job.objects.count(), 2)

    def test_handoff_provenance_survives_retry(self):
        """A downstream retry retains its original workflow source link."""

        source = self.completed_translation()
        handoff = self.client.post(f"/jobs/{source.id}/handoffs/{HANDOFF_URL}/")
        target = Job.objects.get(pk=handoff.data["id"])
        set_job_state(target, JobStatus.FAILED, 10, "Retryable failure.", "JOB_TIMEOUT")

        response = self.client.post(f"/jobs/{target.id}/retry/")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Job.objects.get(pk=response.data["id"]).source_job, source)

    def test_handoff_requires_source_ownership(self):
        """Staff-independent ownership prevents reuse of another user's artifact."""

        source = self.completed_translation(owner=self.other_user)

        response = self.client.post(f"/jobs/{source.id}/handoffs/{HANDOFF_URL}/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Job.objects.count(), 1)

    def test_tampered_output_is_rejected_before_target_creation(self):
        """Fingerprint mismatches fail closed without parsing or copying bytes."""

        source = self.completed_translation()
        with source.output_file.storage.open(source.output_file.name, "wb") as output:
            output.write(b"tampered-private-output")

        response = self.client.post(f"/jobs/{source.id}/handoffs/{HANDOFF_URL}/")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "JOB_OUTPUT_INTEGRITY_FAILED")
        self.assertEqual(Job.objects.count(), 1)

    def test_incomplete_job_has_no_handoff(self):
        """Queued or output-free jobs cannot enter a downstream workflow."""

        source, _created = create_job(
            self.user, "word.translate", "Translate", {"translate_type": "tr2en"}, word_upload()
        )

        detail = self.client.get(f"/jobs/{source.id}/")
        response = self.client.post(f"/jobs/{source.id}/handoffs/{HANDOFF_URL}/")

        self.assertEqual(detail.data["handoffs"], [])
        self.assertEqual(response.status_code, 404)

    def completed_translation(self, owner=None):
        """Create a succeeded translation with a fingerprinted private output."""

        source, _created = create_job(
            owner or self.user,
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
