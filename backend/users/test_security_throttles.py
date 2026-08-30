"""Enumeration resistance and abuse controls for public credential endpoints."""

from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient

from .password_reset_notifications import pad_password_reset_response
from .throttles import (
    AdminLoginAddressThrottle,
    LoginAccountThrottle,
    LoginAddressThrottle,
    PasswordResetAccountThrottle,
    PasswordResetAddressThrottle,
    PasswordResetCapabilityThrottle,
    PasswordResetConfirmAddressThrottle,
)


class PasswordResetEnumerationResistanceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def test_response_padding_uses_a_fixed_minimum_duration(self):
        with (
            patch(
                "users.password_reset_notifications.time.monotonic",
                return_value=100.05,
            ),
            patch("users.password_reset_notifications.time.sleep") as sleep_mock,
        ):
            pad_password_reset_response(100.0)

        sleep_mock.assert_called_once()
        self.assertAlmostEqual(sleep_mock.call_args.args[0], 0.15)

    def test_known_and_unknown_requests_use_the_same_public_response_path(self):
        user = get_user_model().objects.create_user(
            username="known-reset-user",
            email="known@example.invalid",
            password="StrongPass!123",
        )
        with patch("users.views.pad_password_reset_response") as pad_mock:
            known = self.client.post(
                "/api/users/password-reset/",
                {"email": user.email},
                format="json",
            )
            unknown = self.client.post(
                "/api/users/password-reset/",
                {"email": "unknown@example.invalid"},
                format="json",
            )

        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(pad_mock.call_count, 2)

    def test_password_reset_request_is_throttled_by_client_address(self):
        with (
            patch.object(PasswordResetAddressThrottle, "rate", "2/hour"),
            patch.object(PasswordResetAccountThrottle, "rate", "100/hour"),
            patch("users.views.pad_password_reset_response"),
        ):
            responses = [
                self.client.post(
                    "/api/users/password-reset/",
                    {"email": f"unknown-{index}@example.invalid"},
                    format="json",
                )
                for index in range(3)
            ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 429])
        self.assertEqual(responses[-1].data["code"], "THROTTLED")

    def test_password_reset_confirmation_is_throttled_by_capability(self):
        payload = {"uid": "invalid", "token": "invalid-token", "new_password": "Strong!123"}
        with (
            patch.object(PasswordResetConfirmAddressThrottle, "rate", "100/hour"),
            patch.object(PasswordResetCapabilityThrottle, "rate", "2/hour"),
        ):
            responses = [
                self.client.post(
                    "/api/users/password-reset/confirm/",
                    payload,
                    format="json",
                )
                for _index in range(3)
            ]

        self.assertEqual([response.status_code for response in responses], [400, 400, 429])
        self.assertEqual(responses[-1].data["code"], "THROTTLED")


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def test_browser_login_is_throttled_by_submitted_account(self):
        csrf_response = self.client.get("/api/session/")
        csrf_token = csrf_response.cookies["csrftoken"].value
        with (
            patch.object(LoginAddressThrottle, "rate", "100/minute"),
            patch.object(LoginAccountThrottle, "rate", "2/minute"),
        ):
            responses = [
                self.client.post(
                    "/api/session/",
                    {"username": "unknown", "password": "invalid"},
                    format="json",
                    HTTP_X_CSRFTOKEN=csrf_token,
                )
                for _index in range(3)
            ]

        self.assertEqual(responses[-1].status_code, 429)
        self.assertEqual(responses[-1].data["code"], "THROTTLED")

    def test_admin_login_is_throttled_before_authentication(self):
        request = RequestFactory().post(
            "/admin/login/",
            {"username": "operator", "password": "invalid"},
            REMOTE_ADDR="127.0.0.1",
        )
        with patch.object(AdminLoginAddressThrottle, "rate", "1/minute"):
            self.assertTrue(AdminLoginAddressThrottle().allow_request(request, admin.site))
            response = admin.site.login(request)

        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
