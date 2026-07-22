import json

from jobs.models import Job
from word.analysis_contracts import CUSTOM_CHECK_PREFIX, MAX_CUSTOM_CHECKS, MAX_QUESTION_LENGTH

from .base import JobTestCase
from .test_document_jobs import word_upload


class DocumentAnalysisChecklistApiTests(JobTestCase):
    """Verify profile persistence, validation, and owner isolation."""

    def test_checklist_requires_authentication(self):
        """Anonymous callers cannot inspect or mutate profile questions."""

        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get("/word/analysis-checks/").status_code, 401)
        self.assertEqual(
            self.client.post("/word/analysis-checks/", {"question": "Private?"}).status_code,
            401,
        )

    def test_saved_questions_are_profile_scoped_and_deletable(self):
        """Only the owner can list or delete a profile checklist entry."""

        created = self.client.post(
            "/word/analysis-checks/", {"question": "  Is the hazard log referenced?  "}
        )
        identifier = created.data["id"]
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["question"], "Is the hazard log referenced?")
        self.assertEqual(self.checklist(), [created.data])

        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.checklist(), [])
        self.assertEqual(self.client.delete(self.detail_url(identifier)).status_code, 404)

        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(self.detail_url(identifier)).status_code, 204)
        self.assertEqual(self.checklist(), [])

    def test_blank_and_duplicate_questions_are_rejected(self):
        """Invalid profile data is rejected without replacing saved entries."""

        first = self.client.post(
            "/word/analysis-checks/", {"question": "Is the source identified?"}
        )
        blank = self.client.post("/word/analysis-checks/", {"question": "   "})
        duplicate = self.client.post(
            "/word/analysis-checks/", {"question": "is the source identified?"}
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(len(self.checklist()), 1)

    def test_reset_preferences_clears_saved_questions(self):
        """A profile reset restores the custom checklist default."""

        self.save_question("Is the source identified?")

        response = self.client.post("/auth/preferences/reset/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.checklist(), [])

    def test_question_length_and_saved_count_are_bounded(self):
        """Profile checklist limits bound storage and analyzer work."""

        oversized = self.client.post(
            "/word/analysis-checks/", {"question": "x" * (MAX_QUESTION_LENGTH + 1)}
        )
        for index in range(MAX_CUSTOM_CHECKS):
            self.assertEqual(self.save_response(f"Question {index}?").status_code, 201)
        overflow = self.save_response("One question too many?")

        self.assertEqual(oversized.status_code, 400)
        self.assertEqual(overflow.status_code, 400)
        self.assertEqual(len(self.checklist()), MAX_CUSTOM_CHECKS)

    def test_custom_question_is_snapshotted_into_the_owned_job(self):
        """A saved owner question becomes immutable private job input."""

        saved = self.save_question("Is a safety rationale provided?")
        identifier = f"{CUSTOM_CHECK_PREFIX}{saved['id']}"
        response = self.enqueue(["approvals", identifier])
        self.client.delete(self.detail_url(saved["id"]))

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.parameters["check_ids"], ["approvals", identifier])
        self.assertEqual(job.parameters["custom_checks"], [saved])

    def test_user_cannot_analyze_another_users_saved_question(self):
        """Custom identifiers never authorize cross-profile checklist access."""

        self.client.force_authenticate(self.other_user)
        saved = self.save_question("Is owner-only evidence present?")
        self.client.force_authenticate(self.user)

        response = self.enqueue([f"{CUSTOM_CHECK_PREFIX}{saved['id']}"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Job.objects.count(), 0)

    def checklist(self):
        """Return the current authenticated user's checklist payload."""

        return self.client.get("/word/analysis-checks/").data["results"]

    def save_question(self, question):
        """Create one saved question and return its response payload."""

        return self.save_response(question).data

    def save_response(self, question):
        """Create one saved question and return the full API response."""

        return self.client.post("/word/analysis-checks/", {"question": question})

    def enqueue(self, check_ids):
        """Queue analysis with the supplied checklist identifiers."""

        return self.client.post(
            "/word/jobs/analyze/",
            {"file": word_upload(), "check_ids": json.dumps(check_ids)},
            format="multipart",
        )

    @staticmethod
    def detail_url(identifier):
        """Return the owner-scoped custom check detail endpoint."""

        return f"/word/analysis-checks/{identifier}/"
