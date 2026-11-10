"""Every browser password writer must produce credentials the login accepts."""

import secrets

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from .password_reset_tokens import token_generator


class PasswordContractTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = " " + secrets.token_urlsafe(24) + " "
        self.user = User.objects.create_user("u10001", password=self.password)
        self.admin = User.objects.create_superuser("a10001", password=secrets.token_urlsafe(24))
        self.api = APIClient()

    def assert_login(self, user, password):
        response = APIClient().post(
            "/api/session/", {"username": user.username, "password": password}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(password))

    def test_password_change_preserves_spaces_and_accepts_128_characters(self):
        password = " " + secrets.token_urlsafe(96)[:126] + " "
        self.api.force_authenticate(self.user)
        response = self.api.post("/api/users/password/", {
            "current_password": self.password, "new_password": password,
            "confirm_password": password,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assert_login(self.user, password)

    def test_password_change_rejects_129_characters_without_changing_password(self):
        password = secrets.token_urlsafe(100)[:129]
        current_password = secrets.token_urlsafe(24)
        self.user.set_password(current_password)
        self.user.save(update_fields=["password"])
        self.api.force_authenticate(self.user)
        response = self.api.post("/api/users/password/", {
            "current_password": current_password, "new_password": password,
            "confirm_password": password,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(current_password))

    def test_admin_api_password_writes_preserve_spaces_and_reject_129_characters(self):
        self.api.force_authenticate(self.admin)
        password = " " + secrets.token_urlsafe(96)[:126] + " "
        created = self.api.post("/api/users/", {"username": "u10002", "password": password}, format="json")
        self.assertEqual(created.status_code, 201)
        target = User.objects.get(pk=created.data["id"])
        self.assert_login(target, password)
        for endpoint, method, payload in (
            ("/api/users/", self.api.post, {"username": "u10003"}),
            (f"/api/users/{target.pk}/", self.api.patch, {}),
        ):
            with self.subTest(endpoint=endpoint):
                response = method(endpoint, {**payload, "password": secrets.token_urlsafe(100)[:129]}, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="u10003").exists())
        self.assert_login(target, password)

    def test_reset_preserves_password_whitespace(self):
        password = " " + secrets.token_urlsafe(96)[:126] + " "
        response = self.api.post("/api/users/password-reset/confirm/", {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": token_generator.make_token(self.user), "new_password": password,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assert_login(self.user, password)

    def test_django_admin_password_change_rejects_129_characters(self):
        self.client.force_login(self.admin)
        password = secrets.token_urlsafe(100)[:129]
        response = self.client.post(
            reverse("admin:auth_user_password_change", args=[self.user.pk]),
            {"password1": password, "password2": password, "usable_password": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_django_admin_creation_rejects_129_characters(self):
        self.client.force_login(self.admin)
        password = secrets.token_urlsafe(100)[:129]
        response = self.client.post(reverse("admin:auth_user_add"), {
            "username": "u10003", "password1": password, "password2": password,
            "usable_password": "true", "_save": "Save",
            "preferences-TOTAL_FORMS": "0", "preferences-INITIAL_FORMS": "0",
            "preferences-MIN_NUM_FORMS": "0", "preferences-MAX_NUM_FORMS": "1",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["adminform"].form.errors.as_data()["password1"][0].code, "max_length")
        self.assertFalse(User.objects.filter(username="u10003").exists())

    def test_django_admin_creation_accepts_password_that_browser_login_can_use(self):
        self.client.force_login(self.admin)
        password = " " + secrets.token_urlsafe(96)[:126] + " "
        response = self.client.post(reverse("admin:auth_user_add"), {
            "username": "u10003", "password1": password, "password2": password,
            "usable_password": "true", "_save": "Save",
            "preferences-TOTAL_FORMS": "0", "preferences-INITIAL_FORMS": "0",
            "preferences-MIN_NUM_FORMS": "0", "preferences-MAX_NUM_FORMS": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.assert_login(User.objects.get(username="u10003"), password)
