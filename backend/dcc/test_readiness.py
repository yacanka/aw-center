"""Unit tests for explainable DCC readiness scoring and acknowledgement."""

from django.test import SimpleTestCase

from dcc.document_snapshot import DccSnapshotError
from dcc.readiness import assess_dcc_readiness, validate_readiness_acknowledgement


class DccReadinessTests(SimpleTestCase):
    """Verify deterministic, content-free readiness decisions."""

    def test_complete_source_is_ready_without_optional_compdocs(self):
        """Optional CompDoc linkage does not lower an otherwise complete DCC."""

        result = assess_dcc_readiness({"panel_count": 2}, [], compliance())

        self.assertEqual(result["readiness_score"], 100)
        self.assertEqual(result["readiness_level"], "ready")
        self.assertFalse(result["requires_readiness_acknowledgement"])
        self.assertEqual(result["readiness_warning_codes"], [])

    def test_missing_source_and_panels_require_review(self):
        """Incomplete source coverage produces weighted actionable warnings."""

        result = assess_dcc_readiness(
            {"panel_count": 0}, ["DCC form number", "responsible AS"], compliance()
        )

        self.assertLess(result["readiness_score"], 100)
        self.assertEqual(result["readiness_level"], "review")
        self.assertEqual(
            set(result["readiness_warning_codes"]),
            {"DCC_SOURCE_FIELDS", "DCC_PANEL_COVERAGE"},
        )

    def test_linked_sources_explain_reference_and_maturity_risk(self):
        """CompDoc quality is scored without returning document content."""

        result = assess_dcc_readiness(
            {"panel_count": 1}, [], compliance(2, missing=1, approved=1)
        )
        codes = {check["code"] for check in result["readiness_checks"]}

        self.assertIn("DCC_COMPDOC_TECH_REFERENCE", codes)
        self.assertIn("DCC_COMPDOC_MATURITY", result["readiness_warning_codes"])
        self.assertNotIn("name", str(result).lower())

    def test_acknowledgement_must_match_every_warning_exactly(self):
        """Confirmation cannot omit or invent a readiness warning code."""

        summary = {"readiness_warning_codes": ["DCC_PANEL_COVERAGE"]}
        accepted = validate_readiness_acknowledgement(
            summary, {"acknowledged_warning_codes": ["DCC_PANEL_COVERAGE"]}
        )

        self.assertEqual(accepted, ["DCC_PANEL_COVERAGE"])
        with self.assertRaises(DccSnapshotError) as raised:
            validate_readiness_acknowledgement(summary, {"acknowledged_warning_codes": []})
        self.assertEqual(raised.exception.code, "DCC_READINESS_ACK_REQUIRED")
        with self.assertRaises(DccSnapshotError) as malformed:
            validate_readiness_acknowledgement(summary, [])
        self.assertEqual(malformed.exception.code, "DCC_READINESS_ACK_INVALID")


def compliance(count=0, missing=0, approved=0):
    """Return the content-free compliance summary consumed by readiness."""

    return {
        "compliance_document_count": count,
        "compliance_documents_without_technical_reference": missing,
        "compliance_document_statuses": {"authority_approved": approved},
    }
