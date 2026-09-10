"""Explainable compliance-document risk scoring tests."""

from datetime import date
from uuid import uuid4

from django.test import SimpleTestCase

from .risk import assess_document_risk


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
            document(target=date(2026, 6, 30)), [("to_be_issued", date(2026, 6, 30))], "delayed", TODAY
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


def document(document_id=None, name="Document", tech_doc_no=None, target=None):
    """Build one value-query shaped document for risk tests."""

    return {
        "id": document_id or uuid4(),
        "name": name,
        "panel": "Panel A",
        "ata": "00-00",
        "tech_doc_no": tech_doc_no,
        "ubm_target_date": target,
    }
