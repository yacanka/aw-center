import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.invitation_service import token_digest
from users.models import UserInvitation

User = get_user_model()


class UserInvitationTests(TestCase):
    """Verify secure creation and single-use invitation acceptance."""

    def setUp(self):
        """Create representative admin, non-admin, group, and API clients."""

        cache.clear()
        self.admin = User.objects.create_superuser(
            "invite-admin", "admin@example.com", "StrongPass!123"
        )
        self.regular = User.objects.create_user(
            "invite-regular", "regular@example.com", "StrongPass!123"
        )
        self.group = Group.objects.create(name="Invited Reviewers")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_only_staff_with_add_user_permission_can_create_invitation(self):
        """Authentication or model permission alone cannot mint links."""

        anonymous = APIClient().post("/auth/invitations/", self._create_payload(), format="json")
        self.regular.user_permissions.add(Permission.objects.get(codename="add_user"))
        self.client.force_authenticate(self.regular)
        regular = self.client.post("/auth/invitations/", self._create_payload(), format="json")

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(regular.status_code, 403)
        self.assertEqual(UserInvitation.objects.count(), 0)

    def test_admin_receives_fragment_link_and_database_stores_only_digest(self):
        """The raw 256-bit token is returned once and never persisted."""

        response, token = self._create_invitation()
        invitation = UserInvitation.objects.get()
        parsed_link = urlsplit(response.data["invitation_link"])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(parsed_link.path, "/app/invite")
        self.assertEqual(parsed_link.query, "")
        self.assertEqual(invitation.token_digest, token_digest(token))
        self.assertNotEqual(invitation.token_digest, token)
        self.assertAlmostEqual(
            invitation.expires_at - invitation.created_at, timedelta(days=1), delta=timedelta(seconds=1)
        )

    def test_valid_token_can_be_inspected_without_authentication(self):
        """The recipient can load only the bound email and expiration context."""

        _, token = self._create_invitation()
        response = APIClient().post(
            "/auth/invitations/inspect/", {"token": token}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "recipient@example.com")
        self.assertNotIn("groups", response.data)

    def test_accepting_invitation_creates_grouped_user_and_consumes_link(self):
        """A successful account creation atomically makes the link unusable."""

        _, token = self._create_invitation()
        anonymous = APIClient()
        response = anonymous.post(
            "/auth/invitations/accept/", self._accept_payload(token), format="json"
        )
        second = anonymous.post(
            "/auth/invitations/accept/", self._accept_payload(token, "another-user"), format="json"
        )

        user = User.objects.get(username="invited-user")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(user.check_password("StrongInvite!123"))
        self.assertTrue(user.groups.filter(pk=self.group.pk).exists())
        self.assertEqual(second.status_code, 410)
        self.assertEqual(second.data["code"], "INVITATION_USED")
        self.assertEqual(UserInvitation.objects.get().used_by, user)

    def test_expired_invitation_cannot_create_an_account(self):
        """The exact 24-hour boundary is rechecked during acceptance."""

        _, token = self._create_invitation()
        UserInvitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = APIClient().post(
            "/auth/invitations/accept/", self._accept_payload(token), format="json"
        )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.data["code"], "INVITATION_EXPIRED")
        self.assertFalse(User.objects.filter(username="invited-user").exists())

    def test_new_link_for_same_email_revokes_previous_link(self):
        """Only the newest administrator-issued link remains usable."""

        _, first_token = self._create_invitation()
        _, second_token = self._create_invitation()
        anonymous = APIClient()

        first = anonymous.post(
            "/auth/invitations/inspect/", {"token": first_token}, format="json"
        )
        second = anonymous.post(
            "/auth/invitations/inspect/", {"token": second_token}, format="json"
        )

        self.assertEqual(first.status_code, 410)
        self.assertEqual(first.data["code"], "INVITATION_REVOKED")
        self.assertEqual(second.status_code, 200)

    def test_invalid_token_and_weak_password_do_not_consume_invitation(self):
        """Failed authorization or validation never changes invitation state."""

        _, token = self._create_invitation()
        invalid = APIClient().post(
            "/auth/invitations/inspect/", {"token": secrets.token_urlsafe(32)}, format="json"
        )
        weak_payload = self._accept_payload(token)
        weak_payload["password"] = weak_payload["password_confirm"] = "password"
        weak = APIClient().post("/auth/invitations/accept/", weak_payload, format="json")

        self.assertEqual(invalid.status_code, 404)
        self.assertEqual(invalid.data["code"], "INVITATION_INVALID")
        self.assertEqual(weak.status_code, 400)
        self.assertIsNone(UserInvitation.objects.get().used_at)

    def test_authenticated_session_cannot_accept_another_users_invitation(self):
        """Recipients must accept from an anonymous browser session."""

        _, token = self._create_invitation()
        response = self.client.post(
            "/auth/invitations/accept/", self._accept_payload(token), format="json"
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="invited-user").exists())

    def test_public_acceptance_attempts_are_rate_limited(self):
        """Repeated token guesses from one client are bounded."""

        client = APIClient()
        payload = self._accept_payload(secrets.token_urlsafe(32))
        responses = [
            client.post("/auth/invitations/accept/", payload, format="json") for _ in range(21)
        ]

        self.assertEqual(responses[-2].status_code, 404)
        self.assertEqual(responses[-1].status_code, 429)

    def test_existing_email_and_unknown_group_are_rejected(self):
        """Invitations cannot create duplicate identities or retain unknown roles."""

        existing = self._create_payload()
        existing["email"] = self.regular.email
        duplicate = self.client.post("/auth/invitations/", existing, format="json")
        invalid_group = self._create_payload()
        invalid_group["group_ids"] = [999999]
        unknown = self.client.post("/auth/invitations/", invalid_group, format="json")

        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(UserInvitation.objects.count(), 0)

    def _create_invitation(self):
        response = self.client.post("/auth/invitations/", self._create_payload(), format="json")
        return response, urlsplit(response.data["invitation_link"]).fragment

    def _create_payload(self):
        return {"email": "recipient@example.com", "group_ids": [self.group.pk]}

    @staticmethod
    def _accept_payload(token, username="invited-user"):
        return {
            "token": token,
            "username": username,
            "first_name": "Invited",
            "last_name": "User",
            "password": "StrongInvite!123",
            "password_confirm": "StrongInvite!123",
        }
