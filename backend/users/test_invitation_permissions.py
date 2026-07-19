from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient


class InvitationPermissionTests(TestCase):
    """Verify the staff and model-permission intersection."""

    def setUp(self):
        """Create one staff account without implicit superuser authority."""

        self.user = get_user_model().objects.create_user(
            "invitation-manager",
            "manager@example.com",
            "StrongPass!123",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_staff_requires_add_user_permission(self):
        """Staff status alone cannot create account invitations."""

        response = self.client.post(
            "/auth/invitations/", {"email": "recipient@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 403)

    def test_staff_with_add_user_permission_can_create_invitation(self):
        """A delegated staff account can create a link without superuser status."""

        self.user.user_permissions.add(Permission.objects.get(codename="add_user"))
        response = self.client.post(
            "/auth/invitations/", {"email": "recipient@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("invitation_link", response.data)
