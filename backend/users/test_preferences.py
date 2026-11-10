"""Appearance resets and account writes must preserve user-owned content."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class PreferenceBoundaryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("preference-owner")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_reset_changes_only_appearance(self):
        preferences = self.user.preferences
        preferences.theme = "dark"
        preferences.has_particles = True
        preferences.language = "tr"
        preferences.email_notifications = False
        preferences.extra_settings = {"other": {"keep": True}, "watcher": {"outstanding_only": True}}
        preferences.save()
        response = self.client.post("/api/users/preferences/reset/")
        self.assertEqual(response.status_code, 200)
        preferences.refresh_from_db()
        self.assertEqual(preferences.theme, "system")
        self.assertFalse(preferences.has_particles)
        self.assertEqual(preferences.language, "tr")
        self.assertFalse(preferences.email_notifications)
        self.assertEqual(preferences.extra_settings, {"other": {"keep": True}})

    def test_account_save_cannot_overwrite_a_newer_theme(self):
        self.assertEqual(self.user.preferences.theme, "system")
        self.client.patch("/api/users/preferences/", {"theme": "dark"}, format="json")
        # This user carries a stale cached related object, just like a concurrent request.
        self.user.preferences.theme = "system"
        self.user.first_name = "Changed"
        self.user.save(update_fields=["first_name"])
        self.assertEqual(self.client.get("/api/users/preferences/").data["theme"], "dark")

    def test_general_preferences_cannot_mutate_content_or_feature_json(self):
        for payload in ({"jira_list": []}, {"document_analysis_checks": []}, {"extra_settings": {}}):
            response = self.client.patch("/api/users/preferences/", payload, format="json")
            self.assertEqual(response.status_code, 400, payload)
        self.assertNotIn("jira_list", self.client.get("/api/users/preferences/").data)
        self.assertNotIn("document_analysis_checks", self.client.get("/api/users/preferences/").data)

    def test_reset_preserves_saved_questions(self):
        created = self.client.post("/api/tools/word/analysis-checks/", {"question": "Check the source?"})
        self.assertEqual(created.status_code, 201)
        self.client.post("/api/users/preferences/reset/")
        self.assertEqual(self.client.get("/api/tools/word/analysis-checks/").data["results"], [created.data])
