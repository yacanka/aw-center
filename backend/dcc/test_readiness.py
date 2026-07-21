"""Unit tests for explainable DCC readiness scoring and acknowledgement."""

from django.test import SimpleTestCase

from dcc.document_snapshot import DccSnapshotError
from dcc.readiness import assess_dcc_readiness, validate_readiness_acknowledgement


class DccReadinessTests(SimpleTestCase):
    """Verify deterministic, content-free readiness decisions."""

    def test_complete_source_is_ready(self):
        """A complete DCC source is ready without human warning acknowledgement."""

        result = assess_dcc_readiness({"panel_count": 2}, [])

        self.assertEqual(result["readiness_score"], 100)
        self.assertEqual(result["readiness_level"], "ready")
        self.assertFalse(result["requires_readiness_acknowledgement"])
        self.assertEqual(result["readiness_warning_codes"], [])

    def test_missing_source_and_panels_require_review(self):
        """Incomplete source coverage produces weighted actionable warnings."""

        result = assess_dcc_readiness({"panel_count": 0}, ["DCC form number", "responsible AS"])

        self.assertLess(result["readiness_score"], 100)
        self.assertEqual(result["readiness_level"], "review")
        self.assertEqual(
            set(result["readiness_warning_codes"]),
            {"DCC_SOURCE_FIELDS", "DCC_PANEL_COVERAGE"},
        )

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
