import json
from unittest.mock import patch

from jobs.models import Job, JobStatus
from jobs.services import create_job
from jobs.worker import claim_next_job, execute_claimed_job
from word.analysis import ANALYSIS_CHECKS
from word.analysis_results import bounded_score

from .base import JobTestCase
from .test_document_jobs import word_upload


class DocumentAnalysisApiTests(JobTestCase):
    """Verify the durable document-analysis enqueue contract."""

    def test_analysis_job_persists_only_allowlisted_checks(self):
        """The API stores a deduplicated allowlisted checklist."""

        selected = ["approvals", "revision_history", "approvals"]
        response = self.client.post(
            "/word/jobs/analyze/",
            {"file": word_upload(), "check_ids": json.dumps(selected)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.kind, "word.analyze")
        self.assertEqual(job.parameters["check_ids"], selected[:2])

    def test_analysis_job_rejects_empty_or_unknown_checks(self):
        """Invalid checklists fail before private artifacts are persisted."""

        for checks in ([], ["unknown_check"]):
            response = self.client.post(
                "/word/jobs/analyze/",
                {"file": word_upload(), "check_ids": json.dumps(checks)},
                format="multipart",
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Job.objects.count(), 0)


class DocumentAnalysisWorkerTests(JobTestCase):
    """Verify private reports, safe summaries, and model failures."""

    @patch("word.analysis.create_analysis_engine")
    def test_analysis_executor_creates_private_report_and_safe_summary(self, engine_factory):
        """Evidence stays in the artifact while the API exposes scores only."""

        engine_factory.return_value = FakeAnalysisEngine()
        job, _ = create_job(
            self.user,
            "word.analyze",
            "Analyze",
            {"check_ids": ["approvals", "attachments"]},
            word_upload(),
        )

        execute_claimed_job(claim_next_job("analysis-worker"))

        job.refresh_from_db()
        self._assert_private_report(job)

    def _assert_private_report(self, job):
        """Assert content separation between summary and private artifact."""

        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(job.result_summary["type"], "document_analysis")
        self.assertNotIn("evidence", json.dumps(job.result_summary))
        self.assertNotIn("secret-path", json.dumps(job.result_summary))
        with job.output_file.open("rb") as output:
            report = json.loads(output.read().decode("utf-8"))
        self.assertEqual(len(report["checks"]), 2)
        self.assertEqual(report["checks"][0]["evidence"][0]["text"], "Approval evidence")
        self.assertNotIn("file_path", report["checks"][0]["evidence"][0])

    @patch("word.analysis.ExplainableDocxRetriever", side_effect=OSError("secret model path"))
    def test_analysis_executor_sanitizes_missing_model_failure(self, _retriever):
        """Missing models create a retryable safe recovery contract."""

        job, _ = create_job(
            self.user,
            "word.analyze",
            "Analyze",
            {"check_ids": list(ANALYSIS_CHECKS)},
            word_upload(),
        )

        execute_claimed_job(claim_next_job("analysis-worker"))

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "WORD_ANALYZER_MODEL_UNAVAILABLE")
        self.assertTrue(job.retryable)
        self.assertNotIn("secret model path", job.message)

    def test_non_finite_model_scores_are_safely_bounded(self):
        """NaN, infinity, and malformed values never enter JSON contracts."""

        self.assertEqual(bounded_score(float("nan")), 0.0)
        self.assertEqual(bounded_score(float("inf")), 0.0)
        self.assertEqual(bounded_score("invalid"), 0.0)


class FakeAnalysisEngine:
    """Provide deterministic retrieval output without loading local models."""

    def __init__(self):
        self.units = [{"text": "Approval evidence"}]

    def add_docx_file(self, _source, _name):
        """Accept the materialized test document."""

    def build_index(self):
        """Represent successful local index creation."""

    def search(self, _query):
        """Return explainable evidence including a path that must be removed."""

        return {
            "best_score": 0.9,
            "explanation": "Strong local evidence.",
            "results": [{
                "text": "Approval evidence",
                "final_score": 0.9,
                "metadata": {"source_type": "paragraph", "file_path": "/secret-path"},
            }],
        }
