"""Browser-only Django session and CSRF contract tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SESSION_COOKIE_SAMESITE="Lax",
    CSRF_COOKIE_SAMESITE="Lax",
)
class SessionCsrfTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user(
            username="session-user",
            password="StrongPass!123",
            email="session@example.com",
        )

    def csrf_token(self):
        response = self.client.get("/api/session/")
        self.assertEqual(response.status_code, 200)
        return response.cookies["csrftoken"].value

    def login(self):
        token = self.csrf_token()
        return self.client.post(
            "/api/session/",
            {"username": "session-user", "password": "StrongPass!123"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

    def test_bootstrap_sets_csrf_cookie_without_auth_cache(self):
        response = self.client.get("/api/session/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"state": "anonymous", "user": None})
        self.assertIn("csrftoken", response.cookies)

    def test_login_requires_csrf(self):
        response = self.client.post(
            "/api/session/",
            {"username": "session-user", "password": "StrongPass!123"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_login_uses_http_only_session_cookie_and_exposes_no_token(self):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "authenticated")
        self.assertEqual(response.data["user"]["username"], "session-user")
        self.assertNotIn("token", response.data)
        self.assertTrue(response.cookies["sessionid"]["httponly"])

        bootstrap = self.client.get("/api/session/")
        self.assertEqual(bootstrap.data["state"], "authenticated")

    def test_logout_requires_csrf_and_invalidates_server_session(self):
        self.assertEqual(self.login().status_code, 200)

        rejected = self.client.delete("/api/session/")
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(self.client.get("/api/session/").data["state"], "authenticated")

        token = self.client.cookies["csrftoken"].value
        accepted = self.client.delete(
            "/api/session/",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(accepted.status_code, 204)
        self.assertEqual(self.client.get("/api/session/").data["state"], "anonymous")

    def test_authorization_header_is_not_a_browser_auth_fallback(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token debug-token")

        response = self.client.get("/api/users/preferences/")

        self.assertIn(response.status_code, {401, 403})
