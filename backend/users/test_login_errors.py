"""Secure session-login error contract tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(CSRF_COOKIE_SECURE=False)
class LoginErrorContractTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user(
            "known-user", "known@example.com", "StrongPass!123"
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def _login(self, username, password=None):
        token = self.client.get("/api/session/").cookies["csrftoken"].value
        payload = {"username": username}
        if password is not None:
            payload["password"] = password
        return self.client.post(
            "/api/session/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

    def test_rejected_credentials_return_authentication_contract(self):
        response = self._login("known-user", "WrongPass!123")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "AUTHENTICATION_FAILED")

    def test_unknown_and_known_accounts_have_same_public_failure(self):
        known = self._login("known-user", "WrongPass!123")
        unknown = self._login("unknown-user", "WrongPass!123")

        self.assertEqual(known.data["detail"], unknown.data["detail"])
        self.assertEqual(known.data["code"], unknown.data["code"])

    def test_missing_field_remains_a_validation_error(self):
        response = self._login("known-user")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        self.assertIn("password", response.data["errors"])
