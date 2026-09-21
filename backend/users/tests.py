"""User administration and local-development command tests."""

import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from users.admin import (
    ConstrainedAdminAuthenticationForm,
    ConstrainedUserChangeForm,
    ConstrainedUserCreationForm,
)
from users.models import UserPreferences


User = get_user_model()


class UserAdministrationTests(TestCase):
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

    def test_preferences_keep_list_defaults(self):
        preferences = UserPreferences.objects.get(user=self.regular_user)
        preferences.jira_list = {"invalid": "shape"}
        preferences.save(update_fields=["jira_list"])

        preferences.reset_to_defaults()

        self.assertEqual(preferences.jira_list, [])

    def test_anonymous_user_cannot_list_or_create_users(self):
        listed = self.client.get("/api/users/")
        created = self.client.post(
            "/api/users/",
            {"username": "u10003", "password": "StrongPass!123"},
            format="json",
        )

        self.assertIn(listed.status_code, {401, 403})
        self.assertIn(created.status_code, {401, 403})
        self.assertFalse(User.objects.filter(username="u10003").exists())

    def test_admin_can_assign_permission_and_group(self):
        permission = Permission.objects.get(codename="change_user")
        group = Group.objects.create(name="Auditors")
        self.client.force_authenticate(self.admin_user)

        response = self.client.patch(
            f"/api/users/{self.target_user.pk}/",
            {"user_permissions": [permission.pk], "groups": [group.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertTrue(self.target_user.user_permissions.filter(pk=permission.pk).exists())
        self.assertTrue(self.target_user.groups.filter(pk=group.pk).exists())

    def test_regular_user_cannot_assign_permissions(self):
        permission = Permission.objects.get(codename="change_user")
        self.client.force_authenticate(self.regular_user)

        response = self.client.patch(
            f"/api/users/{self.regular_user.pk}/",
            {"user_permissions": [permission.pk]},
            format="json",
        )

        self.assertIn(response.status_code, {400, 403})
        self.assertFalse(self.regular_user.user_permissions.filter(pk=permission.pk).exists())

    def test_user_api_enforces_username_format_on_creation_and_change(self):
        self.client.force_authenticate(self.admin_user)
        for username in ("123456", "u1234", "u123456", "uu2345", "u1234x", "u123_5"):
            with self.subTest(username=username):
                response = self.client.post(
                    "/api/users/",
                    {"username": username, "password": "StrongPass!123"},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("username", response.data["errors"])
        valid = self.client.post(
            "/api/users/",
            {"username": "Ş12345", "password": "StrongPass!123"},
            format="json",
        )
        self.assertEqual(valid.status_code, 201)

        legacy = User.objects.create_user("legacy-user", password="StrongPass!123")
        unchanged = self.client.patch(
            f"/api/users/{legacy.pk}/",
            {"username": "legacy-user", "first_name": "Updated"},
            format="json",
        )
        invalid_change = self.client.patch(
            f"/api/users/{legacy.pk}/", {"username": "invalid-name"}, format="json"
        )
        self.assertEqual(unchanged.status_code, 400)
        self.assertEqual(invalid_change.status_code, 400)
        legacy.refresh_from_db()
        self.assertEqual((legacy.username, legacy.first_name), ("legacy-user", ""))

    def test_django_admin_forms_apply_rule_to_existing_users(self):
        valid = ConstrainedUserCreationForm(
            data={"username": "Ğ12345", "password1": "StrongPass!123", "password2": "StrongPass!123"}
        )
        invalid = ConstrainedUserCreationForm(
            data={"username": "admin-user", "password1": "StrongPass!123", "password2": "StrongPass!123"}
        )
        self.assertNotIn("username", valid.errors)
        self.assertIn("username", invalid.errors)

        legacy = User.objects.create_user("legacy-user")
        unchanged = ConstrainedUserChangeForm(data={"username": "legacy-user"}, instance=legacy)
        changed = ConstrainedUserChangeForm(data={"username": "invalid-name"}, instance=legacy)
        self.assertIn("username", unchanged.errors)
        self.assertIn("username", changed.errors)

    def test_admin_login_form_rejects_legacy_username(self):
        legacy = User.objects.create_superuser("legacy-user", password="StrongPass!123")
        form = ConstrainedAdminAuthenticationForm(
            data={"username": legacy.username, "password": "StrongPass!123"}
        )

        self.assertIn("username", form.errors)


class DevelopmentUserCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_command_creates_debug_only_login_user(self):
        password = secrets.token_urlsafe(24)
        call_command(
            "ensure_development_user",
            username="u20002",
            password=password,
            verbosity=0,
        )

        user = User.objects.get(username="u20002")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(password))

    @override_settings(DEBUG=True)
    def test_command_requires_an_explicit_password(self):
        with self.assertRaisesMessage(CommandError, "--password"):
            call_command("ensure_development_user", verbosity=0)

    @override_settings(DEBUG=True)
    def test_command_rejects_invalid_username(self):
        with self.assertRaisesMessage(CommandError, "one letter followed"):
            call_command(
                "ensure_development_user",
                username="legacy-user",
                password="StrongPass!123",
                verbosity=0,
            )

    @override_settings(DEBUG=False)
    def test_command_rejects_non_debug_settings(self):
        with self.assertRaisesMessage(CommandError, "DEBUG=True"):
            call_command("ensure_development_user", verbosity=0)
