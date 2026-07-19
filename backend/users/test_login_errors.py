from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class LoginErrorContractTests(TestCase):
    """Verify secure and actionable login failure semantics."""

    def setUp(self):
        """Create one account without exposing its existence through errors."""

        get_user_model().objects.create_user(
            "known-user", "known@example.com", "StrongPass!123"
        )
        self.client = APIClient()

    def test_rejected_credentials_return_authentication_contract(self):
        """Valid-shaped but incorrect credentials are authentication failures."""

        response = self._login("known-user", "WrongPass!123")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "AUTHENTICATION_FAILED")
        self.assertFalse(response.data["retryable"])
        self.assertIn("credentials", response.data["recovery_hint"])

    def test_unknown_and_known_accounts_have_same_public_failure(self):
        """Login errors never disclose whether a username exists."""

        known = self._login("known-user", "WrongPass!123")
        unknown = self._login("unknown-user", "WrongPass!123")

        self.assertEqual(known.data["detail"], unknown.data["detail"])
        self.assertEqual(known.data["code"], unknown.data["code"])
        self.assertEqual(known.data["recovery_hint"], unknown.data["recovery_hint"])

    def test_missing_field_remains_a_validation_error(self):
        """Malformed requests retain field-level correction guidance."""

        response = self.client.post("/auth/token/", {"username": "known-user"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        self.assertIn("password", response.data["errors"])

    def _login(self, username, password):
        return self.client.post(
            "/auth/token/", {"username": username, "password": password}, format="json"
        )
