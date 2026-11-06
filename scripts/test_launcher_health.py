"""Live health changes do not create duplicate ready events or kill processes."""
import unittest

from scripts.launcher import installation_readiness as readiness


class HealthTests(unittest.TestCase):
    def test_three_failed_rounds_degrade_and_two_successes_recover(self):
        self.assertTrue(hasattr(readiness, 'HealthMonitor'), 'Live health monitor is missing')
        events = []
        results = iter([False, False, False, True, False, True, True])
        now = [0]
        monitor = readiness.HealthMonitor(lambda: next(results), events.append, clock=lambda: now[0])
        for second in (10, 20):
            now[0] = second
            monitor()
        self.assertFalse(any(not event['healthy'] for event in events))
        now[0] = 30
        monitor()
        self.assertFalse(events[-1]['healthy'])
        for second in (40, 50, 60):
            now[0] = second
            monitor()
            self.assertFalse(events[-1]['healthy'])
        now[0] = 70
        monitor()
        self.assertTrue(events[-1]['healthy'])
        self.assertTrue(all(event['type'] == 'health' for event in events))

    def test_checks_are_rate_limited_without_sleeping(self):
        self.assertTrue(hasattr(readiness, 'HealthMonitor'), 'Live health monitor is missing')
        checks = []
        now = [0]
        monitor = readiness.HealthMonitor(lambda: checks.append(1) or True, lambda _: None, clock=lambda: now[0])
        for _ in range(50):
            monitor()
        self.assertEqual(checks, [])
        now[0] = 10
        monitor()
        monitor()
        self.assertEqual(checks, [1])


class ReadinessDiagnosticTests(unittest.TestCase):
    def probe_failure(self, error):
        from unittest import mock
        messages = []
        with mock.patch.object(readiness, 'build_opener') as opener:
            opener.return_value.open.side_effect = error
            self.assertFalse(readiness.probe_http('https://127.0.0.1/health/ready/', diagnostic=messages.append))
        self.assertEqual(len(messages), 1)
        self.assertNotIn('private-detail', messages[0])
        return messages[0]

    def test_certificate_failure_is_distinguished_from_connection_timeout(self):
        import ssl
        from urllib.error import URLError
        error = ssl.SSLCertVerificationError(1, 'private-detail')
        error.verify_code = 20
        self.assertIn('TLS sertifika doğrulaması', self.probe_failure(URLError(error)))
        self.assertIn('20', self.probe_failure(URLError(error)))
        self.assertIn('zaman aşımı', self.probe_failure(URLError(TimeoutError('private-detail'))))

    def test_refused_connection_is_distinguished_from_tls(self):
        from urllib.error import URLError
        self.assertIn('bağlantı reddedildi', self.probe_failure(URLError(ConnectionRefusedError('private-detail'))))

    def test_http_status_and_allowlisted_readiness_dependencies_are_reported(self):
        from io import BytesIO
        from urllib.error import HTTPError
        error = HTTPError('https://private-detail', 503, 'private-detail', {},
                          BytesIO(b'{"checks":{"database":true,"cache":false,"frontend":false,"private-detail":false}}'))
        message = self.probe_failure(error)
        self.assertIn('HTTP 503', message)
        self.assertIn('önbellek', message)
        self.assertIn('frontend dosyaları', message)
        self.assertNotIn('veritabanı', message)

    def test_redirect_is_reported_without_disclosing_destination(self):
        from io import BytesIO
        from urllib.error import HTTPError
        self.assertIn('HTTP 302', self.probe_failure(HTTPError('https://private-detail', 302,
                      'private-detail', {'Location': 'https://private-detail'}, BytesIO(b''))))

    def test_prod_timeout_reports_https_and_last_connection_failure(self):
        from unittest import mock
        from pathlib import Path
        from urllib.error import URLError
        process = mock.Mock()
        process.poll.return_value = None
        profile = {'name': 'prod', 'host': '127.0.0.1', 'backend_port': 8443}
        events = []
        with mock.patch.object(readiness, 'build_opener') as opener:
            opener.return_value.open.side_effect = URLError(TimeoutError('private-detail'))
            with self.assertRaises(readiness.StartupReadinessError) as raised:
                readiness.wait_until_ready([process], profile, Path('missing'), timeout=0, progress=events.append)
        self.assertIn('backend HTTPS', str(raised.exception))
        self.assertIn('zaman aşımı', str(raised.exception))
        self.assertNotIn('private-detail', str(raised.exception))
        self.assertIn('zaman aşımı', events[-1])

    def test_malformed_503_response_still_reports_status_without_body(self):
        from io import BytesIO
        from urllib.error import HTTPError
        message = self.probe_failure(HTTPError('https://private-detail', 503, 'private-detail', {},
                                             BytesIO(b'private-detail' * 1000)))
        self.assertEqual(message, 'HTTP 503')

    def test_success_retains_certificate_verification_and_has_no_failure_diagnostic(self):
        from unittest import mock
        messages = []
        with mock.patch.object(readiness, 'local_server_context') as context, \
             mock.patch.object(readiness, 'HTTPSHandler') as https, \
             mock.patch.object(readiness, 'build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.status = 200
            self.assertTrue(readiness.probe_http('https://127.0.0.1/health/ready/', 'approved.pem',
                                                 diagnostic=messages.append))
        context.assert_called_once_with('approved.pem')
        https.assert_called_once_with(context=context.return_value)
        self.assertEqual(messages, [])
