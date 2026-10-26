"""Legacy ambiguity must not authorize a previously queued password-reset email."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from .email_test_utils import set_legacy_email
from .models import PasswordResetDelivery
from .password_reset_notifications import enqueue_password_reset, process_password_reset_deliveries


class LegacyEmailOutboxTests(TestCase):
    def test_queued_reset_for_legacy_ambiguous_address_is_cancelled_without_sending(self):
        users = get_user_model()
        owner = users.objects.create_user('u89001', email='legacy@example.invalid')
        delivery, created = enqueue_password_reset(owner)
        self.assertTrue(created)
        other = users.objects.create_user('u89002', email='other@example.invalid')
        set_legacy_email(other, 'LEGACY@example.invalid')
        with patch('users.password_reset_notifications.send_html_email') as send:
            result = process_password_reset_deliveries()
        self.assertEqual(result['sent'], 0)
        self.assertEqual(send.call_count, 0)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PasswordResetDelivery.Status.CANCELLED)
        self.assertEqual(delivery.error_code, 'ACCOUNT_UNAVAILABLE')
