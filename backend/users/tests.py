from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()


class UserSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.regular_user = User.objects.create_user(
            username="u10001",
            password="StrongPass!123",
            email="regular@example.com",
        )
        self.target_user = User.objects.create_user(
            username="u10002",
            password="StrongPass!123",
            email="target@example.com",
        )
        self.admin_user = User.objects.create_superuser(
            username="admin1",
            password="StrongPass!123",
            email="admin@example.com",
        )

        self.change_user_permission = Permission.objects.get(codename="change_user")

    def test_anonymous_user_cannot_list_users(self):
        response = self.client.get("/auth/users/")
        self.assertEqual(response.status_code, 401)

    def test_signup_rejects_privilege_fields(self):
        payload = {
            "username": "u10003",
            "password": "StrongPass!123",
            "email": "signup@example.com",
            "user_permissions": [self.change_user_permission.id],
        }
        response = self.client.post("/auth/users/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="u10003").exists())

    def test_signup_without_privilege_fields_creates_regular_user(self):
        payload = {
            "username": "u10004",
            "password": "StrongPass!123",
            "email": "signup2@example.com",
            "first_name": "New",
            "last_name": "User",
        }
        response = self.client.post("/auth/users/", payload, format="json")
        self.assertEqual(response.status_code, 201)

        created_user = User.objects.get(username="u10004")
        self.assertFalse(created_user.is_staff)
        self.assertFalse(created_user.is_superuser)
        self.assertEqual(created_user.user_permissions.count(), 0)

    def test_debug_cookie_defaults_support_plain_http_refresh(self):
        from awcenter.settings import get_default_auth_cookie_samesite
        from awcenter.settings import get_default_auth_cookie_secure

        self.assertEqual(get_default_auth_cookie_samesite(True), "Lax")
        self.assertFalse(get_default_auth_cookie_secure(True))

    def test_production_cookie_defaults_support_secure_cross_site_spa(self):
        from awcenter.settings import get_default_auth_cookie_samesite
        from awcenter.settings import get_default_auth_cookie_secure

        self.assertEqual(get_default_auth_cookie_samesite(False), "None")
        self.assertTrue(get_default_auth_cookie_secure(False))

    @override_settings(AUTH_COOKIE_SAMESITE="Lax", AUTH_COOKIE_SECURE=False)
    def test_login_sets_http_only_cookie_without_exposing_token(self):
        response = self.client.post(
            "/auth/token/",
            {"username": "u10001", "password": "StrongPass!123"},
            format="json",
        )

        auth_cookie = response.cookies["auth_token"]
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("token", response.data)
        self.assertEqual(response.data["user"]["username"], "u10001")
        self.assertEqual(auth_cookie["httponly"], True)
        self.assertEqual(auth_cookie["samesite"], "Lax")

    @override_settings(AUTH_TOKEN_RESPONSE_ENABLED=True)
    def test_login_can_return_token_for_development_header_fallback(self):
        response = self.client.post(
            "/auth/token/",
            {"username": "u10001", "password": "StrongPass!123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)
        self.assertTrue(response.data["token"])

    @override_settings(AUTH_COOKIE_SAMESITE="None", AUTH_COOKIE_SECURE=True)
    def test_login_can_set_cross_site_secure_cookie_policy(self):
        response = self.client.post(
            "/auth/token/",
            {"username": "u10001", "password": "StrongPass!123"},
            format="json",
        )

        auth_cookie = response.cookies["auth_token"]
        self.assertEqual(auth_cookie["samesite"], "None")
        self.assertEqual(auth_cookie["secure"], True)

    def test_login_ignores_stale_auth_cookie(self):
        self.client.cookies["auth_token"] = "stale-token"

        response = self.client.post(
            "/auth/token/",
            {"username": "u10001", "password": "StrongPass!123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["username"], "u10001")
        self.assertNotEqual(response.cookies["auth_token"].value, "stale-token")

    def test_login_response_user_does_not_include_sensitive_fields(self):
        response = self.client.post(
            "/auth/token/",
            {"username": "u10001", "password": "StrongPass!123"},
            format="json",
        )

        user_data = response.data["user"]
        self.assertNotIn("password", user_data)
        self.assertNotIn("auth_token", user_data)

    def test_me_accepts_cookie_after_login(self):
        self.client.post(
            "/auth/token/",
            {"username": "u10001", "password": "StrongPass!123"},
            format="json",
        )

        response = self.client.get("/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "u10001")

    def test_protected_endpoint_rejects_stale_cookie_as_unauthenticated(self):
        self.client.cookies["auth_token"] = "stale-token"

        response = self.client.get("/auth/preferences/")

        self.assertEqual(response.status_code, 401)

    def test_protected_endpoint_accepts_valid_auth_cookie(self):
        token = Token.objects.create(user=self.regular_user)
        self.client.cookies["auth_token"] = token.key

        response = self.client.get("/auth/preferences/")

        self.assertEqual(response.status_code, 200)


    @override_settings(AUTH_COOKIE_NAME="custom_auth_token")
    def test_me_accepts_configured_auth_cookie_name(self):
        token = Token.objects.create(user=self.regular_user)
        self.client.cookies["custom_auth_token"] = token.key

        response = self.client.get("/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "u10001")

    def test_invalid_login_returns_readable_validation_error(self):
        response = self.client.post(
            "/auth/token/",
            {"username": "u10001", "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)
        self.assertIn("code", response.data)

    def test_anonymous_logout_is_idempotent_and_deletes_cookie(self):
        self.client.cookies["auth_token"] = "stale-token"

        response = self.client.post("/auth/logout/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("auth_token", response.cookies)
        self.assertEqual(response.cookies["auth_token"].value, "")

    def test_authenticated_logout_deletes_server_token(self):
        token = Token.objects.create(user=self.regular_user)
        self.client.cookies["auth_token"] = token.key

        response = self.client.post("/auth/logout/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.regular_user).exists())

    def test_regular_user_cannot_escalate_permissions_via_me_endpoint(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.patch(
            "/auth/me/",
            {"user_permissions": [self.change_user_permission.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.regular_user.refresh_from_db()
        self.assertFalse(
            self.regular_user.user_permissions.filter(id=self.change_user_permission.id).exists()
        )

    def test_admin_can_assign_permissions(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.patch(
            f"/auth/users/{self.target_user.pk}/",
            {"user_permissions": [self.change_user_permission.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertTrue(
            self.target_user.user_permissions.filter(id=self.change_user_permission.id).exists()
        )
