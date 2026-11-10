"""Self-service profile writes are limited to the authenticated user's identity fields."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class ProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="U12345", email="profile@example.com", first_name="Before"
        )
        self.other = get_user_model().objects.create_user("U54321", email="other@example.com")
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.client.get("/api/session/")
        self.token = self.client.cookies["csrftoken"].value

    def patch(self, payload):
        return self.client.patch(
            "/api/users/profile/", payload, format="json", HTTP_X_CSRFTOKEN=self.token
        )

    def test_updates_own_profile_and_session_without_changing_preferences(self):
        response = self.patch({"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ada")
        self.assertEqual(self.user.last_name, "Lovelace")
        self.assertEqual(self.user.email, "ada@example.com")
        self.assertEqual(self.user.preferences.theme, "system")
        session = self.client.get("/api/session/").data["user"]
        self.assertEqual(session["email"], "ada@example.com")
        self.other.refresh_from_db()
        self.assertEqual(self.other.email, "other@example.com")

    def test_partial_update_and_blank_names(self):
        response = self.patch({"first_name": ""})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "")
        self.assertEqual(self.user.email, "profile@example.com")

    def test_rejects_invalid_fields_atomically(self):
        for payload in (
            {"email": "invalid"}, {"email": ""}, {"email": "a" * 255 + "@example.com"},
            {"first_name": "a" * 151}, {"last_name": "a" * 151},
            {"is_staff": True}, {"is_superuser": True}, {"user_permissions": []},
            {"groups": []}, {"password": "ignored"}, {"username": "U99999"},
            {"id": self.other.pk}, {"preferences": {"theme": "dark"}},
        ):
            with self.subTest(fields=list(payload)):
                response = self.patch({"last_name": "Must not persist", **payload})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["code"], "VALIDATION_ERROR")
                self.user.refresh_from_db()
                self.assertEqual(self.user.last_name, "")
                self.assertFalse(self.user.is_staff)

    def test_rejects_another_accounts_email_case_insensitively(self):
        response = self.patch({"email": "OTHER@example.com", "first_name": "Must not persist"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data["errors"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profile@example.com")
        self.assertEqual(self.user.first_name, "Before")

    def test_accepts_own_unchanged_email(self):
        response = self.patch({"email": self.user.email, "last_name": "Updated"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, "Updated")

    def test_requires_authentication_and_csrf(self):
        response = self.client.patch("/api/users/profile/", {"first_name": "Blocked"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        self.assertIn(self.patch({"first_name": "Blocked"}).status_code, (401, 403))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Before")
