from django.test import SimpleTestCase
from automations.ecr_effectivity import add_effectivity_suggestion
from integrations.jira.effectivity import find_closest_option, normalize_effectivity_text


class EffectivitySuggestionTests(SimpleTestCase):
    def metadata(self):
        return [{"id": "customfield_34115", "schema": {"type": "array", "items": "option"},
                 "allowedValues": [{"id": "41", "value": "4AV 1-12"}, {"id": "42", "value": "4AV-80"}]}]

    def test_groups_become_reviewable_jira_option_ids(self):
        result = {"fields": [], "ready": True}
        add_effectivity_suggestion(result, self.metadata(), "1-12, 80 (4AV)")
        self.assertEqual(result["effectivity_suggestion"], {"values": ["41", "42"], "labels": ["4AV 1-12", "4AV-80"]})
        self.assertTrue(result["ready"])
        self.assertFalse(result["fields"][0]["required"])

    def test_unmatched_values_are_not_silently_dropped_or_substituted(self):
        result = {"fields": []}
        add_effectivity_suggestion(result, self.metadata(), "1-12, 99 (4AV)")
        self.assertNotIn("effectivity_suggestion", result)
        self.assertEqual(find_closest_option("4AV-81", ["4AV-80"]), "4AV-81")

    def test_missing_metadata_and_empty_input_offer_nothing(self):
        for metadata, value in (([], "4AV 1-12"), (self.metadata(), "")):
            self.assertEqual(add_effectivity_suggestion({"fields": []}, metadata, value), {"fields": []})
        self.assertEqual(normalize_effectivity_text("1-12, 80 (4AV)"), "4AV 1-12; 4AV-80")
