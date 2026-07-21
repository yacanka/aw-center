"""Explainable compliance-document risk scoring tests."""

from datetime import date
from uuid import UUID, uuid4

from django.test import SimpleTestCase

from common.compdoc_dashboard import build_compdoc_dashboard
from common.compdoc_risk import assess_document_risk


TODAY = date(2026, 7, 22)


class CompDocRiskAssessmentTests(SimpleTestCase):
    """Verify deterministic scoring and reason disclosure."""

    def test_combines_authority_aging_resubmissions_and_missing_reference(self):
        """Independent risk signals produce one bounded explainable score."""

        entries = [
            ("to_be_issued", date(2026, 1, 1)),
            ("to_be_re-submitted", date(2026, 2, 1)),
            ("to_be_updated", date(2026, 3, 1)),
            ("to_be_re-submitted", date(2026, 4, 1)),
            ("authority_review", date(2026, 5, 1)),
        ]

        risk = assess_document_risk(document(), entries, "authority_review", TODAY)

        self.assertEqual(risk["score"], 65)
        self.assertEqual(risk["level"], "high")
        self.assertEqual(risk["stage_age_days"], 82)
        self.assertEqual(
            [signal["code"] for signal in risk["signals"]],
            ["authority_aging", "resubmission_cycle", "missing_technical_reference"],
        )
        self.assertTrue(all(signal["detail"] for signal in risk["signals"]))
        self.assertNotIn("tech_doc_no", risk)

    def test_scores_target_overdue_and_long_wait_without_double_counting(self):
        """Target breach and active-stage wait use distinct workflow semantics."""

        overdue = assess_document_risk(
            document(), [("to_be_issued", date(2026, 6, 30))], "delayed", TODAY
        )
        waiting = assess_document_risk(
            document(tech_doc_no="TD-1"),
            [("to_be_issued", date(2026, 1, 1)), ("to_be_updated", date(2026, 6, 1))],
            "to_be_updated",
            TODAY,
        )

        self.assertEqual(overdue["score"], 45)
        self.assertEqual(overdue["level"], "medium")
        self.assertEqual([item["code"] for item in overdue["signals"]], [
            "sla_target_overdue",
            "missing_technical_reference",
        ])
        self.assertEqual(waiting["score"], 12)
        self.assertEqual(waiting["signals"][0]["code"], "long_wait")

    def test_approved_document_with_reference_has_no_risk(self):
        """Completed referenced documents remain outside the priority queue."""

        risk = assess_document_risk(
            document(tech_doc_no="TD-1"),
            [("authority_approved", date(2026, 1, 1))],
            "authority_approved",
            TODAY,
        )

        self.assertEqual(risk["score"], 0)
        self.assertEqual(risk["level"], "none")
        self.assertEqual(risk["signals"], [])

    def test_accepts_project_specific_secondary_technical_reference(self):
        """Dual-document projects are not penalized when either reference exists."""

        values = document()
        values["tech_doc_no_2"] = "TD-SECONDARY"
        risk = assess_document_risk(
            values,
            [("authority_approved", date(2026, 1, 1))],
            "authority_approved",
            TODAY,
        )

        self.assertEqual(risk["score"], 0)


class CompDocRiskAggregationTests(SimpleTestCase):
    """Verify bounded project summaries and deterministic ordering."""

    def test_bounds_priorities_without_losing_distribution(self):
        """Large projects retain aggregate counts while limiting response size."""

        rows = [
            document(
                document_id=UUID(int=index + 1),
                name=f"Document {index:02d}",
                status_flow=[{"status": "authority_approved", "date": "01.01.2026"}],
            )
            for index in range(30)
        ]

        risk = build_compdoc_dashboard(RowQuerySet(rows), today=TODAY)["risk"]

        self.assertEqual(risk["counts"], {"high": 0, "medium": 0, "low": 30, "none": 0})
        self.assertEqual(risk["at_risk_count"], 30)
        self.assertEqual(risk["average_score"], 15)
        self.assertEqual(len(risk["priorities"]), 25)
        self.assertEqual(risk["priorities"][0]["name"], "Document 00")
        self.assertEqual(risk["policy"]["version"], 1)


class RowQuerySet:
    """Minimal iterator contract used by the streaming dashboard builder."""

    def __init__(self, rows):
        self.rows = rows

    def iterator(self, chunk_size):
        """Return rows without database setup."""

        self.chunk_size = chunk_size
        return iter(self.rows)


def document(document_id=None, name="Document", tech_doc_no=None, status_flow=None):
    """Build one value-query shaped document for risk tests."""

    return {
        "id": document_id or uuid4(),
        "name": name,
        "panel": "Panel A",
        "ata": "00-00",
        "tech_doc_no": tech_doc_no,
        "status_flow": status_flow or [],
    }
