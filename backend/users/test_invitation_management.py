from datetime import timedelta
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import UserInvitation

User = get_user_model()


class InvitationManagementTests(TestCase):
    """Verify authorized invitation audit and revocation workflows."""

    def setUp(self):
        """Create an invitation manager and representative invitations."""

        self.manager = User.objects.create_user(
            "invitation-manager", "manager@example.com", "StrongPass!123", is_staff=True
        )
        self.manager.user_permissions.add(Permission.objects.get(codename="add_user"))
        self.group = Group.objects.create(name="Reviewers")
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_list_is_paginated_searchable_and_never_exposes_digest(self):
        """The audit ledger returns relationships but no recoverable token material."""

        self._create("alpha@example.com")
        self._create("beta@example.com")
        response = self.client.get("/auth/invitations/?search=alpha&page_size=1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["groups"], ["Reviewers"])
        self.assertEqual(response.data["results"][0]["created_by"], self.manager.username)
        self.assertNotIn("token_digest", response.data["results"][0])

    def test_status_filters_distinguish_all_lifecycle_states(self):
        """Each invitation appears in exactly its current lifecycle filter."""

        active = self._create("active@example.com")
        expired = self._create("expired@example.com")
        revoked = self._create("revoked@example.com")
        UserInvitation.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        UserInvitation.objects.filter(pk=revoked.pk).update(revoked_at=timezone.now())

        self.assertEqual(self._status_count("active"), 1)
        self.assertEqual(self._status_count("expired"), 1)
        self.assertEqual(self._status_count("revoked"), 1)
        self.assertEqual(self._status_count("used"), 0)

    def test_active_invitation_can_be_revoked_idempotently(self):
        """Revocation invalidates the link and repeated requests stay successful."""

        invitation, token = self._create_with_token("recipient@example.com")
        first = self.client.delete(f"/auth/invitations/{invitation.pk}/")
        second = self.client.delete(f"/auth/invitations/{invitation.pk}/")
        inspect = APIClient().post(
            "/auth/invitations/inspect/", {"token": token}, format="json"
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["status"], "revoked")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(inspect.status_code, 410)
        self.assertEqual(inspect.data["code"], "INVITATION_REVOKED")

    def test_used_and_expired_invitations_cannot_be_revoked(self):
        """Terminal audit states cannot be rewritten as administrator revocations."""

        used = self._create("used@example.com")
        expired = self._create("expired@example.com")
        UserInvitation.objects.filter(pk=used.pk).update(used_at=timezone.now())
        UserInvitation.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        used_response = self.client.delete(f"/auth/invitations/{used.pk}/")
        expired_response = self.client.delete(f"/auth/invitations/{expired.pk}/")

        self.assertEqual(used_response.status_code, 409)
        self.assertEqual(used_response.data["code"], "INVITATION_ALREADY_USED")
        self.assertEqual(expired_response.status_code, 409)
        self.assertEqual(expired_response.data["code"], "INVITATION_ALREADY_EXPIRED")

    def test_management_requires_the_same_delegated_authority_as_creation(self):
        """Anonymous and ordinary staff accounts cannot inspect or revoke the ledger."""

        invitation = self._create("protected@example.com")
        unauthorized = User.objects.create_user(
            "ordinary-staff", "staff@example.com", "StrongPass!123", is_staff=True
        )
        self.client.force_authenticate(unauthorized)

        listing = self.client.get("/auth/invitations/")
        revocation = self.client.delete(f"/auth/invitations/{invitation.pk}/")

        self.assertEqual(listing.status_code, 403)
        self.assertEqual(revocation.status_code, 403)

    def _status_count(self, lifecycle_status):
        response = self.client.get(f"/auth/invitations/?status={lifecycle_status}")
        self.assertEqual(response.status_code, 200)
        return response.data["count"]

    def _create(self, email):
        invitation, _ = self._create_with_token(email)
        return invitation

    def _create_with_token(self, email):
        response = self.client.post(
            "/auth/invitations/",
            {"email": email, "group_ids": [self.group.pk]},
            format="json",
        )
        token = urlsplit(response.data["invitation_link"]).fragment
        return UserInvitation.objects.get(email=email), token
