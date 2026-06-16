from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()


class CookieTokenCsrfTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = User.objects.create_superuser(
            username="csrf_user",
            password="StrongPass!123",
            email="csrf@example.com",
            first_name="Before",
        )
        token = Token.objects.create(user=self.user)
        self.client.cookies["auth_token"] = token.key

    def test_cookie_post_requires_csrf_token(self):
        response = self.client.post("/auth/logout/", format="json")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Token.objects.filter(user=self.user).exists())

    def test_cookie_post_accepts_valid_csrf_token(self):
        csrf_token = self._set_valid_csrf_cookie()

        response = self.client.post(
            "/auth/logout/",
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_cookie_put_requires_csrf_token(self):
        response = self.client.put(
            "/auth/preferences/",
            {"items_per_page": 25},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_cookie_put_accepts_valid_csrf_token(self):
        csrf_token = self._set_valid_csrf_cookie()

        response = self.client.put(
            "/auth/preferences/",
            {"items_per_page": 25},
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_cookie_patch_requires_csrf_token(self):
        response = self.client.patch(
            "/auth/me/",
            {"first_name": "After"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_cookie_patch_accepts_valid_csrf_token(self):
        csrf_token = self._set_valid_csrf_cookie()

        response = self.client.patch(
            "/auth/me/",
            {"first_name": "After"},
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "After")

    def test_cookie_delete_requires_csrf_token(self):
        response = self.client.delete(f"/auth/users/{self.user.id}/", format="json")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(id=self.user.id).exists())

    def test_cookie_delete_accepts_valid_csrf_token(self):
        csrf_token = self._set_valid_csrf_cookie()

        response = self.client.delete(
            f"/auth/users/{self.user.id}/",
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(id=self.user.id).exists())

    def test_header_token_post_does_not_require_csrf_token(self):
        token = Token.objects.get(user=self.user)
        self.client.cookies.clear()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.post("/auth/logout/", format="json")

        self.assertEqual(response.status_code, 200)

    def _set_valid_csrf_cookie(self):
        self.client.cookies.pop("auth_token", None)
        response = self.client.post(
            "/auth/token/",
            {"username": "csrf_user", "password": "StrongPass!123"},
            format="json",
        )
        csrf_token = response.cookies["csrftoken"].value
        self.client.cookies["auth_token"] = response.cookies["auth_token"].value
        self.client.cookies["csrftoken"] = csrf_token
        return csrf_token
