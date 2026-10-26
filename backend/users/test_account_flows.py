"""Account identity and deletion must preserve recovery and audit boundaries."""

import secrets
import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.forms import modelform_factory
from django.test import TestCase
from rest_framework.test import APIClient

from compliance.models import CoverPageNumberAllocation
from orgs.models import Project

from .admin import ConstrainedUserChangeForm, ConstrainedUserCreationForm
from .models import PasswordResetDelivery
from .email_test_utils import set_legacy_email


User = get_user_model()


class AccountEmailIdentityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser("a41001")
        self.user = User.objects.create_user("u41001", email="owner@example.invalid")
        self.other = User.objects.create_user("u41002", email="other@example.invalid")
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_administration_create_rejects_case_insensitive_duplicate_email(self):
        response = self.api.post("/api/users/", {
            "username": "u41003", "email": "OWNER@example.invalid",
            "password": secrets.token_urlsafe(24),
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data["errors"])
        self.assertFalse(User.objects.filter(username="u41003").exists())

    def test_administration_update_rejects_duplicate_email_atomically(self):
        response = self.api.patch(f"/api/users/{self.other.pk}/", {
            "email": "OWNER@example.invalid", "first_name": "Must not persist",
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.other.refresh_from_db()
        self.assertEqual(self.other.email, "other@example.invalid")
        self.assertEqual(self.other.first_name, "")

    def test_administration_preserves_blank_email_and_unchanged_identity(self):
        for email in ("OWNER@example.invalid", "", "new@example.invalid"):
            with self.subTest(email=email):
                response = self.api.patch(
                    f"/api/users/{self.user.pk}/", {"email": email}, format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.user.refresh_from_db()
                self.assertEqual(self.user.email, email)
        response = self.api.post("/api/users/", {
            "username": "u41003", "password": secrets.token_urlsafe(24),
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["email"], "")

    def test_unchanged_legacy_duplicate_does_not_block_unrelated_profile_edit(self):
        set_legacy_email(self.other, self.user.email)
        response = self.api.patch(f"/api/users/{self.other.pk}/", {
            "email": self.other.email, "first_name": "Updated",
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.other.refresh_from_db()
        self.assertEqual(self.other.first_name, "Updated")

    def test_admin_change_form_rejects_duplicate_email(self):
        form_class = modelform_factory(
            User, form=ConstrainedUserChangeForm, fields=("username", "email"),
        )
        form = form_class(instance=self.other, data={
            "username": self.other.username, "email": "OWNER@example.invalid",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_admin_creation_form_checks_email_when_the_field_is_included(self):
        form_class = modelform_factory(
            User, form=ConstrainedUserCreationForm, fields=("username", "email"),
        )
        password = secrets.token_urlsafe(24)
        form = form_class(data={
            "username": "u41003", "email": "OWNER@example.invalid",
            "password1": password, "password2": password, "usable_password": "true",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_admin_form_keeps_blank_and_unchanged_legacy_email_editable(self):
        set_legacy_email(self.other, self.user.email)
        form_class = modelform_factory(
            User, form=ConstrainedUserChangeForm, fields=("username", "email", "first_name"),
        )
        for email in (self.other.email, ""):
            with self.subTest(email=email):
                form = form_class(instance=self.other, data={
                    "username": self.other.username, "email": email, "first_name": "Updated",
                })
                self.assertTrue(form.is_valid(), form.errors)
                saved = form.save()
                self.assertEqual(saved.email, email)
                self.assertEqual(saved.first_name, "Updated")

    def test_ambiguous_legacy_reset_is_neutral_and_does_not_choose_an_account(self):
        set_legacy_email(self.other, self.user.email.upper())
        self.api.force_authenticate(None)
        for other_active in (True, False):
            with self.subTest(other_active=other_active):
                self.other.is_active = other_active
                self.other.save(update_fields=["is_active"])
                ambiguous = self.api.post("/api/users/password-reset/", {
                    "email": self.user.email,
                }, format="json")
                unknown = self.api.post("/api/users/password-reset/", {
                    "email": "unknown@example.invalid",
                }, format="json")
                self.assertEqual(ambiguous.status_code, 200)
                self.assertEqual(ambiguous.data, unknown.data)
                self.assertFalse(PasswordResetDelivery.objects.exists())

    def test_unique_active_reset_still_enqueues_for_the_owner(self):
        self.api.force_authenticate(None)
        response = self.api.post("/api/users/password-reset/", {
            "email": self.user.email.upper(),
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PasswordResetDelivery.objects.get().user_id, self.user.pk)


class ProtectedAccountDeletionTests(TestCase):
    def test_number_allocation_returns_conflict_and_preserves_audit_and_account(self):
        admin = User.objects.create_superuser("a42001")
        user = User.objects.create_user("u42001")
        allocation = CoverPageNumberAllocation.objects.create(
            project=Project.objects.first(), actor=user, client_operation_id=uuid.uuid4(),
            request_hash="synthetic-request", document_snapshot={}, format_code="test",
            credential_fingerprint="synthetic",
        )
        client = APIClient()
        client.force_authenticate(admin)

        response = client.delete(f"/api/users/{user.pk}/")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "USER_HAS_PROTECTED_RECORDS")
        self.assertIn("deactivate", response.data["detail"].lower())
        self.assertNotIn("CoverPageNumberAllocation", str(response.data))
        self.assertNotIn("ProtectedError", str(response.data))
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        self.assertTrue(CoverPageNumberAllocation.objects.filter(pk=allocation.pk).exists())

    def test_unreferenced_account_can_still_be_deleted(self):
        admin = User.objects.create_superuser("a42001")
        user = User.objects.create_user("u42001")
        client = APIClient()
        client.force_authenticate(admin)

        response = client.delete(f"/api/users/{user.pk}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
