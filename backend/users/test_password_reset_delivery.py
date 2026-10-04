"""Password-reset outbox durability, fencing, and secret-handling tests."""

import html
import json
import re
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from integrations.mail import MailUnavailable

from .models import PasswordResetDelivery
from .password_reset_notifications import (
    claim_password_reset_deliveries,
    deliver_password_reset,
    enqueue_password_reset,
    process_password_reset_deliveries,
)


User = get_user_model()


@override_settings(
    FRONTEND_RESET_URL="https://awcenter.invalid/app/login",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="no-reply@awcenter.invalid",
)
class PasswordResetDeliveryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="reset-user",
            email="reset-user@example.invalid",
            password="StrongPass!123",
        )

    @override_settings(AWCENTER_MAIL_TRANSPORT="disabled")
    def test_public_request_queues_without_mail_secret_or_account_disclosure(self):
        known = self.client.post(
            "/api/users/password-reset/",
            {"email": self.user.email},
            format="json",
        )
        duplicate = self.client.post(
            "/api/users/password-reset/",
            {"email": self.user.email},
            format="json",
        )
        unknown = self.client.post(
            "/api/users/password-reset/",
            {"email": "unknown@example.invalid"},
            format="json",
        )

        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(duplicate.data, known.data)
        self.assertEqual(PasswordResetDelivery.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(AWCENTER_MAIL_TRANSPORT="django")
    def test_worker_delivers_stable_link_that_can_reset_password(self):
        self.client.post(
            "/api/users/password-reset/",
            {"email": self.user.email},
            format="json",
        )
        delivery_id, lease_token = claim_password_reset_deliveries()[0]

        outcome = deliver_password_reset(delivery_id, lease_token)

        self.assertEqual(outcome, PasswordResetDelivery.Status.SENT)
        delivery = PasswordResetDelivery.objects.get(pk=delivery_id)
        self.assertEqual(delivery.status, PasswordResetDelivery.Status.SENT)
        self.assertEqual(mail.outbox[0].extra_headers["Message-ID"], delivery.message_id)
        body = html.unescape(mail.outbox[0].alternatives[0].content)
        self.assertIn("/app/login#uid=", body)
        self.assertNotIn("/app/login?uid=", body)
        match = re.search(r"#uid=([^&]+)&token=([^\"<]+)", body)
        self.assertIsNotNone(match)
        uid, token = match.groups()
        persisted = json.dumps(
            PasswordResetDelivery.objects.values().get(pk=delivery_id),
            default=str,
        )
        self.assertNotIn(token, persisted)

        confirmation_payload = {
            "uid": uid,
            "token": token,
            "new_password": "AnotherStrongPass!456",
        }
        confirmed = self.client.post(
            "/api/users/password-reset/confirm/",
            confirmation_payload,
            format="json",
        )

        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("AnotherStrongPass!456"))
        replay = self.client.post(
            "/api/users/password-reset/confirm/",
            confirmation_payload,
            format="json",
        )
        self.assertEqual(replay.status_code, 400)

    def test_retry_reuses_message_id_and_link_without_persisting_token(self):
        delivery, _created = enqueue_password_reset(self.user)
        delivery_id, first_lease = claim_password_reset_deliveries()[0]
        attempts = []

        def unavailable(_subject, body, _to, **kwargs):
            attempts.append((body, kwargs["message_id"]))
            raise MailUnavailable("disabled")

        with patch(
            "users.password_reset_notifications.send_html_email",
            side_effect=unavailable,
        ):
            self.assertEqual(
                deliver_password_reset(delivery_id, first_lease),
                PasswordResetDelivery.Status.FAILED,
            )

        delivery.refresh_from_db()
        delivery.next_attempt_at = timezone.now()
        delivery.save(update_fields=["next_attempt_at"])
        delivery_id, second_lease = claim_password_reset_deliveries()[0]

        def accepted(_subject, body, _to, **kwargs):
            attempts.append((body, kwargs["message_id"]))

        with patch(
            "users.password_reset_notifications.send_html_email",
            side_effect=accepted,
        ):
            self.assertEqual(
                deliver_password_reset(delivery_id, second_lease),
                PasswordResetDelivery.Status.SENT,
            )

        self.assertEqual(attempts[0], attempts[1])
        self.assertEqual(attempts[0][1], delivery.message_id)

    def test_account_state_change_cancels_claim_without_sending(self):
        delivery, _created = enqueue_password_reset(self.user)
        self.user.set_password("ChangedBeforeDelivery!789")
        self.user.save(update_fields=["password"])
        delivery_id, lease_token = claim_password_reset_deliveries()[0]

        with patch("users.password_reset_notifications.send_html_email") as send_mock:
            outcome = deliver_password_reset(delivery_id, lease_token)

        self.assertEqual(outcome, PasswordResetDelivery.Status.CANCELLED)
        send_mock.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.error_code, "ACCOUNT_STATE_CHANGED")

    def test_stale_lease_cannot_send_or_publish_terminal_state(self):
        delivery, _created = enqueue_password_reset(self.user)
        delivery_id, _lease_token = claim_password_reset_deliveries()[0]

        with patch("users.password_reset_notifications.send_html_email") as send_mock:
            outcome = deliver_password_reset(delivery_id, uuid.uuid4())

        self.assertIsNone(outcome)
        send_mock.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PasswordResetDelivery.Status.CLAIMED)

    @override_settings(AWCENTER_MAIL_TRANSPORT="django")
    def test_timeout_retries_stable_link_and_keeps_next_delivery_unclaimed(self):
        from integrations.mail import send_html_email

        first, _ = enqueue_password_reset(self.user)
        other_user = User.objects.create_user(
            username="other-reset-user", email="other@example.invalid", password="pass",
        )
        second, _ = enqueue_password_reset(other_user)
        attempts = []

        def smtp_send(subject, body, recipients, **kwargs):
            attempts.append((body, kwargs["message_id"]))
            if kwargs["message_id"] == first.message_id:
                second.refresh_from_db()
                self.assertEqual(second.status, PasswordResetDelivery.Status.PENDING)
                raise TimeoutError("private upstream timeout detail")
            send_html_email(subject, body, recipients, **kwargs)

        with patch("users.password_reset_notifications.send_html_email", side_effect=smtp_send):
            result = process_password_reset_deliveries()

        self.assertEqual(result, {"processed": 2, "sent": 1, "failed": 1})
        first.refresh_from_db()
        self.assertEqual(first.error_code, "MAIL_DELIVERY_TIMEOUT")
        self.assertIsNotNone(first.next_attempt_at)
        self.assertIsNone(first.lease_token)
        second.refresh_from_db()
        self.assertEqual(second.status, PasswordResetDelivery.Status.SENT)
        first.next_attempt_at = timezone.now()
        first.save(update_fields=["next_attempt_at"])
        process_password_reset_deliveries()
        first.refresh_from_db()
        self.assertEqual(first.status, PasswordResetDelivery.Status.SENT)
        self.assertEqual(mail.outbox[-1].extra_headers["Message-ID"], attempts[0][1])
        self.assertEqual(mail.outbox[-1].alternatives[0].content, attempts[0][0])

    def test_expired_lease_cannot_send_or_publish(self):
        delivery, _ = enqueue_password_reset(self.user)
        delivery_id, token = claim_password_reset_deliveries()[0]
        PasswordResetDelivery.objects.filter(pk=delivery_id).update(
            claim_expires_at=timezone.now() - timedelta(seconds=1),
        )
        with patch("users.password_reset_notifications.send_html_email") as smtp_send:
            self.assertIsNone(deliver_password_reset(delivery_id, token))
        smtp_send.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PasswordResetDelivery.Status.CLAIMED)

    def test_timeout_after_reclaim_cannot_overwrite_new_lease(self):
        delivery, _ = enqueue_password_reset(self.user)
        delivery_id, token = claim_password_reset_deliveries()[0]
        new_token = uuid.uuid4()

        def timeout_after_reclaim(*args, **kwargs):
            PasswordResetDelivery.objects.filter(pk=delivery_id).update(lease_token=new_token)
            raise TimeoutError()

        with patch(
            "users.password_reset_notifications.send_html_email",
            side_effect=timeout_after_reclaim,
        ):
            self.assertIsNone(deliver_password_reset(delivery_id, token))
        delivery.refresh_from_db()
        self.assertEqual(delivery.lease_token, new_token)
        self.assertEqual(delivery.status, PasswordResetDelivery.Status.CLAIMED)

    def test_timeout_after_lease_expiry_leaves_claim_recoverable(self):
        delivery, _ = enqueue_password_reset(self.user)
        delivery_id, token = claim_password_reset_deliveries()[0]

        def expired_timeout(*args, **kwargs):
            PasswordResetDelivery.objects.filter(pk=delivery_id).update(
                claim_expires_at=timezone.now() - timedelta(seconds=1),
            )
            raise TimeoutError()

        with patch("users.password_reset_notifications.send_html_email", side_effect=expired_timeout):
            self.assertIsNone(deliver_password_reset(delivery_id, token))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PasswordResetDelivery.Status.CLAIMED)
        self.assertEqual(delivery.lease_token, token)
        self.assertEqual(delivery.error_code, "")

    @override_settings(AWCENTER_MAIL_TRANSPORT="django", COMPDOC_NOTIFICATION_BATCH_SIZE=2)
    def test_lease_overrun_is_not_reclaimed_again_in_same_pass(self):
        from integrations.mail import send_html_email

        first, _ = enqueue_password_reset(self.user)
        other = User.objects.create_user(
            "overrun-reset-user", email="other@example.invalid", password="pass",
        )
        second, _ = enqueue_password_reset(other)

        def overrun(subject, body, recipients, **kwargs):
            if kwargs["message_id"] == first.message_id:
                PasswordResetDelivery.objects.filter(pk=first.pk).update(
                    claim_expires_at=timezone.now() - timedelta(seconds=1),
                )
            send_html_email(subject, body, recipients, **kwargs)

        with patch("users.password_reset_notifications.send_html_email", side_effect=overrun):
            process_password_reset_deliveries()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.attempt_count, 1)
        self.assertEqual(first.status, PasswordResetDelivery.Status.CLAIMED)
        self.assertEqual(second.status, PasswordResetDelivery.Status.SENT)
        self.assertEqual(process_password_reset_deliveries()["sent"], 1)
        first.refresh_from_db()
        self.assertEqual(first.status, PasswordResetDelivery.Status.SENT)

    @override_settings(AWCENTER_MAIL_TRANSPORT="django")
    def test_notification_worker_processes_password_reset_outbox(self):
        delivery, _created = enqueue_password_reset(self.user)

        call_command(
            "run_compdoc_notification_worker",
            once=True,
            stdout=StringIO(),
            stderr=StringIO(),
        )

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PasswordResetDelivery.Status.SENT)
        self.assertEqual(len(mail.outbox), 1)
