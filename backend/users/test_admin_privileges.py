"""Django admin must preserve the delegated user-management boundary."""

import secrets

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse


class DjangoAdminPrivilegeTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("s10001", is_staff=True)
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="auth"))
        self.superuser = User.objects.create_superuser("a10001", password=secrets.token_urlsafe(24))
        self.group = Group.objects.create(name="Delegated administrators")
        self.client.force_login(self.staff)

    def test_delegated_admin_cannot_submit_superuser_access(self):
        response = self.client.post(
            reverse("admin:auth_user_change", args=[self.staff.pk]),
            {
                "username": self.staff.username,
                "is_active": "on", "is_staff": "on", "is_superuser": "on",
                "date_joined_0": self.staff.date_joined.strftime("%Y-%m-%d"),
                "date_joined_1": self.staff.date_joined.strftime("%H:%M:%S"),
                "preferences-TOTAL_FORMS": "0", "preferences-INITIAL_FORMS": "0",
                "preferences-MIN_NUM_FORMS": "0", "preferences-MAX_NUM_FORMS": "1",
                "_save": "Save",
            },
        )
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_superuser)
        self.assertEqual(response.status_code, 403)

    def test_delegated_admin_cannot_change_an_administrators_password(self):
        password = secrets.token_urlsafe(24)
        response = self.client.post(
            reverse("admin:auth_user_password_change", args=[self.superuser.pk]),
            {"password1": password, "password2": password, "usable_password": "true"},
        )
        self.superuser.refresh_from_db()
        self.assertFalse(self.superuser.check_password(password))
        self.assertEqual(response.status_code, 403)

    def test_delegated_admin_cannot_grant_permissions_through_groups(self):
        permission = Permission.objects.get(codename="manage_project_roles")
        response = self.client.post(
            reverse("admin:auth_group_change", args=[self.group.pk]),
            {"name": self.group.name, "permissions": [permission.pk], "_save": "Save"},
        )
        self.assertFalse(self.group.permissions.exists())
        self.assertEqual(response.status_code, 403)

    def test_authorized_project_role_manager_retains_subject_autocomplete(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="manage_project_roles"))
        for field, term, expected_id in (
            ("user", self.staff.username, self.staff.pk),
            ("group", self.group.name, self.group.pk),
        ):
            with self.subTest(field=field):
                response = self.client.get(reverse("admin:autocomplete"), {
                    "app_label": "orgs", "model_name": "projectroleassignment",
                    "field_name": field, "term": term,
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn(str(expected_id), [item["id"] for item in response.json()["results"]])

    def test_superuser_can_still_manage_users_and_groups(self):
        self.client.force_login(self.superuser)
        password = secrets.token_urlsafe(24)
        response = self.client.post(
            reverse("admin:auth_user_password_change", args=[self.staff.pk]),
            {"password1": password, "password2": password, "usable_password": "true"},
        )
        self.staff.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.staff.check_password(password))
        response = self.client.post(
            reverse("admin:auth_group_change", args=[self.group.pk]),
            {"name": "Updated group", "_save": "Save"},
        )
        self.group.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.group.name, "Updated group")
