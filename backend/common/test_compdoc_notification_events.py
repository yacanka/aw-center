"""Explainable compliance-document notification-event policy tests."""

from datetime import date, timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase

from common.compdoc_notification_events import detect_events, event_states


class CompDocNotificationEventTests(SimpleTestCase):
    """Verify delivery boundaries and DocProof evidence explanations."""

    def test_overdue_event_explains_elapsed_days(self):
        today = date(2026, 7, 28)
        document = self._document(today - timedelta(days=2))

        active = detect_events(document, self._profile(), today)
        overdue = self._state(document, self._profile(), "overdue", today)

        self.assertEqual(active["overdue"], "2026-07-26")
        self.assertTrue(overdue["applicable"])
        self.assertIn("overdue by 2 day(s)", overdue["detail"])

    def test_due_soon_includes_today_and_seven_day_boundary(self):
        today = date(2026, 7, 28)
        due_today = self._document(today)
        due_boundary = self._document(today + timedelta(days=7))

        self.assertIn("due_soon", detect_events(due_today, self._profile(), today))
        self.assertIn("due_soon", detect_events(due_boundary, self._profile(), today))
        self.assertIn("due today", self._state(due_today, self._profile(), "due_soon", today)["detail"])

    def test_revision_requires_newer_docproof_issue(self):
        document = self._document(None)
        available = self._profile("revision_available", "4")
        current = self._profile("current", "3")

        revision = self._state(document, available, "revision_available", date(2026, 7, 28))
        inactive = self._state(document, current, "revision_available", date(2026, 7, 28))

        self.assertTrue(revision["applicable"])
        self.assertIn("issue 4", revision["detail"])
        self.assertFalse(inactive["applicable"])
        self.assertIn("matches", inactive["detail"])

    @staticmethod
    def _document(target):
        return SimpleNamespace(status="to_be_issued", ubm_target_date=target)

    @staticmethod
    def _profile(status="never_checked", issue=""):
        return SimpleNamespace(docproof_status=status, docproof_issue=issue)

    @staticmethod
    def _state(document, profile, event_type, today):
        return next(
            state for state in event_states(document, profile, today) if state["value"] == event_type
        )
