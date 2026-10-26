"""Stale authenticated requests cannot overwrite newer account credentials."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections, connections
from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .views import PasswordChangeView

User = get_user_model()


class PasswordChangeConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.original = secrets.token_urlsafe(24)
        self.user = User.objects.create_user("u10001", password=self.original)

    def request(self, user, password):
        request = APIRequestFactory().post("/api/users/change-password/", {
            "current_password": self.original,
            "new_password": password,
            "confirm_password": password,
        }, format="json")
        request.session = SessionStore()
        force_authenticate(request, user=user)
        return request

    def test_simultaneous_changes_using_old_password_have_only_one_winner(self):
        ready = Barrier(2)
        replacements = [secrets.token_urlsafe(24), secrets.token_urlsafe(24)]

        def change(password):
            close_old_connections()
            try:
                user = User.objects.get(pk=self.user.pk)
                request = self.request(user, password)
                ready.wait(timeout=10)
                response = PasswordChangeView.as_view()(request)
                return response.status_code, password
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(change, replacements))
        self.assertEqual(sorted(status for status, _ in results), [200, 400])
        self.user.refresh_from_db()
        for status, password in results:
            self.assertEqual(self.user.check_password(password), status == 200)

    def test_request_authenticated_before_password_reset_cannot_overwrite_it(self):
        stale_request = self.request(User.objects.get(pk=self.user.pk), secrets.token_urlsafe(24))
        reset_password = secrets.token_urlsafe(24)
        self.user.set_password(reset_password)
        self.user.save(update_fields=["password"])
        response = PasswordChangeView.as_view()(stale_request)
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(reset_password))

    def test_request_authenticated_before_deactivation_cannot_change_credentials(self):
        stale_request = self.request(User.objects.get(pk=self.user.pk), secrets.token_urlsafe(24))
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        response = PasswordChangeView.as_view()(stale_request)
        self.assertEqual(response.status_code, 404)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.original))
