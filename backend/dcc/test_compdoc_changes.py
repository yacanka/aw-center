"""Tests for value-free DCC-visible CompDoc change explanations."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from .compdoc_changes import compare_captured_compdoc


class CompdocCapturedChangeTests(SimpleTestCase):
    """Verify comparison semantics remain deterministic and content-free."""

    def test_reference_and_workflow_changes_are_categorized(self):
        """Changed DCC fields expose labels and categories, never their values."""

        source = document(tech_doc_issue="A", status="authority_review")
        current = document(tech_doc_issue="Sensitive-B", status="authority_approved")

        result = compare_captured_compdoc(current, source)

        self.assertEqual(result["comparison_status"], "changed")
        self.assertEqual(result["changed_field_count"], 2)
        self.assertEqual(
            [field["category"] for field in result["changed_fields"]],
            ["reference", "workflow"],
        )
        self.assertNotIn("Sensitive-B", str(result))

    def test_non_captured_values_do_not_change_comparison(self):
        """Notes and other non-register metadata cannot create DCC-visible changes."""

        source = document(notes="Old internal note")
        current = document(notes="New internal note")

        result = compare_captured_compdoc(current, source)

        self.assertEqual(result["comparison_status"], "unchanged")
        self.assertFalse(result["captured_fields_changed"])

    def test_missing_source_history_requires_manual_review(self):
        """Purged or unavailable history fails conservatively without field guesses."""

        result = compare_captured_compdoc(document(), None)

        self.assertEqual(result["comparison_status"], "unavailable")
        self.assertEqual(result["changed_fields"], [])


def document(**overrides):
    """Return one minimal object matching the shared CompDoc capture contract."""

    values = {
        "name": "Flight Manual",
        "panel": "Panel A",
        "ata": "27-00",
        "cover_page_no": "CP-1",
        "cover_page_issue": "1",
        "tech_doc_no": "TD-1",
        "tech_doc_issue": "A",
        "responsible": "Owner",
        "status_flow": [{"status": overrides.pop("status", "authority_review")}],
        "notes": "",
    }
    return SimpleNamespace(**{**values, **overrides})
