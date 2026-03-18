from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
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
