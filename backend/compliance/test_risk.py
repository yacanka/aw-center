"""Boundary and aggregation coverage for compliance risk policy v2."""

from datetime import date
from uuid import uuid4

from django.test import SimpleTestCase

from .risk import (
    DEFAULT_RISK_POLICY, _risk_level, accumulate_document_risk,
    assess_document_risk, create_risk_state, serialize_risk,
)

TODAY = date(2026, 7, 22)


def document(**values):
    """Complete metadata with an unreleased target outside the approach window."""
    return {
        "id": uuid4(), "name": "Document", "panel": "Panel A", "ata": "00-00",
        "number": "TD-1", "cover_page_no": "CP-1", "status": "authority_approved",
        "target_date": date(2026, 9, 1), "revised_target_date": None,
        "release_date": None, **values,
    }


def assess(**values):
    return assess_document_risk(document(**values), [], "expected", TODAY)


class CompDocRiskAssessmentTests(SimpleTestCase):
    def test_unreleased_target_boundaries(self):
        for target, points in [
            (date(2026, 4, 21), 100), (date(2026, 4, 22), 100),
            (date(2026, 4, 23), 80), (date(2026, 7, 21), 80),
            (TODAY, 30), (date(2026, 8, 21), 30),
            (date(2026, 8, 22), 0), (date(2026, 8, 23), 0),
        ]:
            with self.subTest(target=target):
                risk = assess(target_date=target)
                self.assertEqual(risk["score"], points)
                self.assertEqual(len(risk["signals"]), int(points > 0))

    def test_revised_target_takes_precedence_and_can_supply_the_only_target(self):
        self.assertEqual(assess(target_date=date(2026, 1, 1),
                                revised_target_date=date(2026, 9, 1))["score"], 0)
        self.assertEqual(assess(revised_target_date=date(2026, 7, 21))["score"], 80)
        self.assertEqual(assess(target_date=None, revised_target_date=TODAY)["score"], 30)

    def test_any_recorded_release_disables_target_timing_points(self):
        for release in (date(2026, 7, 1), TODAY, date(2026, 8, 1)):
            for target in (date(2026, 1, 1), TODAY):
                with self.subTest(release=release, target=target):
                    self.assertEqual(assess(release_date=release, target_date=target)["score"], 0)

    def test_each_missing_field_adds_twenty_points(self):
        fields = {
            "target_date": "missing_target_date", "status": "missing_status",
            "cover_page_no": "missing_cover_page", "panel": "missing_panel", "ata": "missing_ata",
        }
        for key, code in fields.items():
            for empty in ([None] if key == "target_date" else [None, "", "  "]):
                with self.subTest(field=key, empty=empty):
                    risk = assess(**{key: empty})
                    self.assertEqual(risk["score"], 20)
                    self.assertEqual(risk["signals"][0]["code"], code)
                    self.assertEqual(risk["signals"][0]["unit"], "missing")
        self.assertEqual(assess(status="unknown")["score"], 20)
        self.assertEqual(assess(status="custom_review")["score"], 0)

    def test_missing_fields_add_and_scores_are_capped_without_hiding_reasons(self):
        risk = assess(target_date=None, status="unknown", cover_page_no="", panel=None, ata="")
        self.assertEqual(risk["score"], 100)
        self.assertEqual(len(risk["signals"]), 5)
        risk = assess(target_date=date(2026, 7, 21), panel=None, ata=None)
        self.assertEqual(risk["score"], 100)
        self.assertEqual(sum(signal["points"] for signal in risk["signals"]), 120)
        self.assertTrue(all(signal["detail"] for signal in risk["signals"]))

    def test_review_aging_uses_release_and_only_the_highest_tier(self):
        cases = [
            ("authority_review", date(2026, 6, 23), 0),
            ("authority_review", date(2026, 6, 22), 20),
            ("authority_review", date(2026, 5, 23), 20),
            ("authority_review", date(2026, 5, 22), 30),
            ("airworthiness_review", date(2026, 7, 8), 0),
            ("airworthiness_review", date(2026, 7, 7), 20),
            ("airworthiness_review", date(2026, 6, 23), 20),
            ("airworthiness_review", date(2026, 6, 22), 30),
        ]
        for status, release, points in cases:
            with self.subTest(status=status, release=release):
                risk = assess(status=status, release_date=release)
                self.assertEqual(risk["score"], points)
                self.assertEqual(len(risk["signals"]), int(points > 0))
                if points:
                    self.assertEqual(risk["signals"][0]["observed"], (TODAY - release).days)
        for status in ("authority_review", "airworthiness_review"):
            for release in (None, date(2026, 7, 23)):
                self.assertEqual(assess(status=status, release_date=release)["score"], 0)

    def test_calendar_month_thresholds_clip_at_month_end(self):
        today = date(2027, 2, 28)
        for values, expected in [
            ({"target_date": date(2026, 11, 30)}, 100),
            ({"status": "authority_review", "release_date": date(2027, 1, 31)}, 20),
            ({"status": "airworthiness_review", "release_date": date(2027, 1, 31)}, 30),
            ({"target_date": date(2027, 3, 27)}, 30),
            ({"target_date": date(2027, 3, 28)}, 0),
        ]:
            with self.subTest(values=values):
                risk = assess_document_risk(document(**values), [], "expected", today)
                self.assertEqual(risk["score"], expected)

    def test_workflow_age_cycles_and_technical_number_do_not_score(self):
        entries = [("to_be_re-submitted", date(2026, 1, 1)),
                   ("to_be_re-submitted", date(2026, 2, 1))]
        risk = assess_document_risk(document(number=None), entries, "to_be_updated", TODAY)
        self.assertEqual(risk["score"], 0)
        self.assertEqual(risk["level"], "low")
        self.assertEqual(risk["signals"], [])
        self.assertEqual(risk["stage_age_days"], 171)
        self.assertNotIn("number", risk)

    def test_review_and_missing_signals_add_independently(self):
        risk = assess(status="authority_review", release_date=date(2026, 5, 22),
                      target_date=None, cover_page_no="")
        self.assertEqual(risk["score"], 70)
        self.assertEqual(risk["level"], "high")
        self.assertEqual(len(risk["signals"]), 3)

    def test_risk_level_boundaries(self):
        for score, level in [(0, "low"), (29, "low"), (30, "medium"), (69, "medium"),
                             (70, "high"), (89, "high"), (90, "very_high"), (100, "very_high")]:
            with self.subTest(score=score):
                self.assertEqual(_risk_level(score, DEFAULT_RISK_POLICY), level)

    def test_zero_scores_are_low_but_only_positive_scores_enter_bounded_priorities(self):
        state = create_risk_state()
        for index in reversed(range(30)):
            accumulate_document_risk(state, document(name=f"Document {index:02}", target_date=None),
                                     [], "expected", TODAY, DEFAULT_RISK_POLICY)
        accumulate_document_risk(state, document(), [], "expected", TODAY, DEFAULT_RISK_POLICY)
        result = serialize_risk(state, 31)
        self.assertEqual(result["counts"], {"very_high": 0, "high": 0, "medium": 0, "low": 31})
        self.assertEqual(result["at_risk_count"], 30)
        self.assertEqual(result["average_score"], 19.4)
        self.assertEqual(len(result["priorities"]), 25)
        self.assertEqual([item["name"] for item in result["priorities"]],
                         [f"Document {index:02}" for index in range(25)])
        self.assertEqual(result["policy"], {"version": 2, "very_high_score": 90, "high_score": 70,
                                          "medium_score": 30, "max_score": 100, "priority_limit": 25})
