"""Outbound SMTP waits must be bounded, including a silent peer."""

import socket
import time
from threading import Event, Thread

from django.core.mail import get_connection
from django.test import SimpleTestCase, override_settings

from integrations.mail import send_html_email


class SmtpTimeoutTests(SimpleTestCase):
    def test_default_smtp_connection_has_a_finite_timeout(self):
        connection = get_connection("django.core.mail.backends.smtp.EmailBackend")

        self.assertIsNotNone(connection.timeout)
        self.assertGreater(connection.timeout, 0)
        self.assertLessEqual(connection.timeout, 30)

    def test_silent_smtp_greeting_times_out(self):
        release_peer = Event()
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(3)

        def silent_peer():
            with listener:
                peer, _address = listener.accept()
                with peer:
                    release_peer.wait(timeout=2)

        server = Thread(target=silent_peer, daemon=True)
        server.start()
        try:
            with override_settings(
                AWCENTER_MAIL_TRANSPORT="django",
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST="127.0.0.1",
                EMAIL_PORT=listener.getsockname()[1],
                EMAIL_HOST_USER="",
                EMAIL_HOST_PASSWORD="",
                EMAIL_USE_TLS=False,
                EMAIL_USE_SSL=False,
                EMAIL_TIMEOUT=0.1,
            ):
                started = time.monotonic()
                with self.assertRaises(TimeoutError):
                    send_html_email("Test", "<p>Test</p>", ["recipient@example.invalid"])
                self.assertLess(time.monotonic() - started, 1.5)
        finally:
            release_peer.set()
            server.join(timeout=3)

        self.assertFalse(server.is_alive())
