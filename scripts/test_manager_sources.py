"""Source diagnostics keep system trust and expose only safe failure categories."""

import io
import json
from dataclasses import replace
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler

from scripts.launcher import installation_sources
from scripts.launcher.installation_sources import Artifact, SourceSettings
from scripts.launcher.process import OperationCancelled
from scripts.manager import worker
from scripts.manager.view_model import ManagerState


class SourceCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.url = 'https://packages.invalid/simple/'
        self.settings = SourceSettings(mode='corporate', python_index_url=self.url)
        self.response = Mock()
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)
        self.response.status = 200
        self.opener = Mock()
        self.opener.open.return_value = self.response
        self.proxies = {}
        self.bypass = False

    def probe(self):
        events = []
        with patch('scripts.launcher.installation.source_settings', return_value=self.settings), \
             patch('urllib.request.build_opener', return_value=self.opener) as factory, \
             patch('urllib.request.getproxies', return_value=self.proxies), \
             patch('urllib.request.proxy_bypass', return_value=self.bypass):
            worker.execute({'action': 'test-sources', 'source_root': str(Path.cwd())},
                           events.append, lambda: None, threading.Event())
        self.assertTrue(events[-1]['ok'], events)
        checks = next(event['checks'] for event in events if event['type'] == 'checks')
        return checks, events, factory

    def test_runtime_download_report_preserves_artifact_and_http_status(self):
        artifact = Artifact('node', '1', 'node.zip', 'https://runtime.invalid/node.zip',
                            'a' * 64, 'zip', 'node.exe')
        for status, remedy in ((401, 'kimlik'), (403, 'erişim'), (407, 'Proxy')):
            with self.subTest(status=status):
                body = io.BytesIO(b'private-response-body')
                events = []
                def download(action, args, emit):
                    args.progress('Yönetilen runtime hazırlığı')
                    installation_sources.fetch_artifact(
                        artifact, self.root.resolve() / str(status), SourceSettings())
                with patch('scripts.manager.operations._dispatch', side_effect=download), \
                     patch.object(installation_sources, '_download', side_effect=HTTPError(
                         'https://private.invalid/opaque', status, 'private-reason', {}, body)):
                    worker.execute({'action': 'bundle'}, events.append, lambda: None, threading.Event())
                error = next(event for event in events if event['type'] == 'error')
                self.assertEqual(error['code'], 'artifact_http_rejected')
                self.assertIn('Node.js', error['message'])
                self.assertIn(f'HTTP {status}', error['message'])
                self.assertIn(remedy, error['remedy'])
                self.assertNotIn('private-', json.dumps(events))
                self.assertTrue(body.closed)
                self.assertEqual(events[-1], {'type': 'done', 'ok': False})

    def test_selected_ca_preserves_system_roots_and_required_verification(self):
        # Use a real local trust anchor without committing a certificate fixture.
        roots = ssl.create_default_context().get_ca_certs(binary_form=True)
        if len(roots) < 2:
            self.skipTest('Requires at least two system/default trusted CA certificates')
        ca_file = self.root / 'selected.pem'
        ca_file.write_text(ssl.DER_cert_to_PEM_cert(roots[0]), encoding='ascii')
        self.settings = replace(self.settings, ca_file=ca_file)
        checks, _, factory = self.probe()
        handler = next(handler for handler in factory.call_args.args if isinstance(handler, HTTPSHandler))
        context = handler._context
        self.assertTrue(set(roots).issubset(context.get_ca_certs(binary_form=True)))
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(checks[0]['status'], 'unverified')

    def test_successful_probe_explains_that_package_download_is_not_verified(self):
        checks, _, _ = self.probe()
        self.assertEqual(checks[0]['status'], 'unverified')
        self.assertIn('örnek paket', checks[0]['detail'].casefold())
        self.assertIn('indirme', checks[0]['detail'])
        self.assertIn('kurulum', checks[0]['detail'])

    def test_without_selected_ca_uses_default_os_certificate_loader(self):
        # The native loader reads Windows CA/ROOT stores (OpenSSL defaults elsewhere).
        with patch.object(ssl.SSLContext, 'load_default_certs', autospec=True) as load:
            _, _, factory = self.probe()
        handler = next(handler for handler in factory.call_args.args if isinstance(handler, HTTPSHandler))
        load.assert_called_once_with(handler._context, ssl.Purpose.SERVER_AUTH)

    def test_selected_ca_is_added_to_existing_trust(self):
        roots = ssl.create_default_context().get_ca_certs(binary_form=True)
        if len(roots) < 2:
            self.skipTest('Requires at least two system/default trusted CA certificates')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(roots[0]))
        ca_file = self.root / 'additional.pem'
        ca_file.write_text(ssl.DER_cert_to_PEM_cert(roots[1]), encoding='ascii')
        self.settings = replace(self.settings, ca_file=ca_file)
        with patch('ssl.create_default_context', return_value=context):
            self.probe()
        self.assertTrue({roots[0], roots[1]}.issubset(context.get_ca_certs(binary_form=True)))

    def test_missing_or_malformed_selected_ca_is_reported_before_network(self):
        invalid = self.root / 'invalid.pem'
        invalid.write_text('not a certificate', encoding='ascii')
        for ca_file in (self.root / 'missing.pem', invalid):
            with self.subTest(ca_file=ca_file):
                self.settings = replace(self.settings, ca_file=ca_file)
                checks, events, _ = self.probe()
                self.assertEqual(checks[0]['status'], 'missing')
                self.assertIn('CA', checks[0]['detail'])
                self.assertIn('PEM', checks[0]['detail'])
                self.assertNotIn(str(ca_file), json.dumps(events))
                self.opener.open.assert_not_called()

    def test_default_trust_loading_failure_has_a_system_ca_diagnostic(self):
        with patch('ssl.create_default_context', side_effect=ssl.SSLError('private-trust-detail')):
            checks, events, _ = self.probe()
        self.assertIn('güven deposu', checks[0]['detail'])
        self.assertNotIn('private-trust-detail', json.dumps(events))
        self.opener.open.assert_not_called()

    def test_certificate_failures_are_distinct_from_other_tls_failures(self):
        for error, expected in (
            (ssl.SSLCertVerificationError('private-cert-detail'), 'CA / sertifika'),
            (URLError(ssl.SSLCertVerificationError('private-cert-detail')), 'CA / sertifika'),
            (ssl.SSLError('private-tls-detail'), 'TLS bağlantısı'),
            (URLError(ssl.SSLError('private-tls-detail')), 'TLS bağlantısı'),
        ):
            with self.subTest(error=type(error)):
                self.opener.open.side_effect = error
                checks, events, _ = self.probe()
                self.assertEqual(checks[0]['status'], 'missing')
                self.assertIn(expected, checks[0]['detail'])
                self.assertNotIn('private-', json.dumps(events))

    def test_http_failures_show_status_and_action_without_response_details(self):
        for code, expected in ((401, 'kimlik'), (403, 'erişim'), (404, 'adres'), (503, 'sunucu')):
            with self.subTest(code=code):
                body = io.BytesIO(b'private-body')
                self.opener.open.side_effect = HTTPError(self.url, code, 'private-reason', {}, body)
                checks, events, _ = self.probe()
                self.assertIn(f'HTTP {code}', checks[0]['detail'])
                self.assertIn(expected, checks[0]['detail'])
                self.assertNotIn('private-', json.dumps(events))
                self.assertTrue(body.closed)

    def test_non_200_response_is_reported_as_http_failure(self):
        self.response.status = 204
        checks, _, _ = self.probe()
        self.assertEqual(checks[0]['status'], 'missing')
        self.assertIn('HTTP 204', checks[0]['detail'])

    def test_proxy_authentication_handles_http_and_https_tunnel_failures(self):
        for error in (
            HTTPError(self.url, 407, 'private-proxy-detail', {}, None),
            URLError(OSError('Tunnel connection failed: 407 private-proxy-detail')),
        ):
            with self.subTest(error=type(error)):
                self.opener.open.side_effect = error
                checks, events, _ = self.probe()
                self.assertIn('Proxy', checks[0]['detail'])
                self.assertIn('407', checks[0]['detail'])
                self.assertIn('kimlik', checks[0]['detail'])
                self.assertNotIn('private-proxy-detail', json.dumps(events))

    def test_other_tunnel_failures_keep_proxy_status_but_not_reason(self):
        self.opener.open.side_effect = URLError(OSError('Tunnel connection failed: 403 private-proxy-detail'))
        checks, events, _ = self.probe()
        self.assertIn('Proxy', checks[0]['detail'])
        self.assertIn('HTTP 403', checks[0]['detail'])
        self.assertNotIn('private-proxy-detail', json.dumps(events))

    def test_direct_dns_timeout_and_connection_errors_have_distinct_diagnostics(self):
        for error, expected in (
            (URLError(socket.gaierror('private-dns-detail')), 'DNS'),
            (URLError(TimeoutError('private-timeout-detail')), 'zaman aşımı'),
            (TimeoutError('private-timeout-detail'), 'zaman aşımı'),
            (URLError(ConnectionRefusedError('private-connection-detail')), 'Bağlantı'),
        ):
            with self.subTest(error=type(error)):
                self.opener.open.side_effect = error
                checks, events, _ = self.probe()
                self.assertIn(expected, checks[0]['detail'])
                self.assertNotIn('private-', json.dumps(events))

    def test_proxy_route_and_bypass_are_respected_without_credential_disclosure(self):
        self.proxies = {'https': 'http://synthetic-user:synthetic-secret@proxy.invalid:8080'}
        self.opener.open.side_effect = URLError(ConnectionRefusedError('private-connection-detail'))
        checks, events, _ = self.probe()
        self.assertIn('Proxy', checks[0]['detail'])
        self.assertNotIn('synthetic-', json.dumps(events))
        self.bypass = True
        checks, _, _ = self.probe()
        self.assertNotIn('Proxy', checks[0]['detail'])
        self.assertIn('Bağlantı', checks[0]['detail'])

    def test_certificate_failure_over_proxy_is_still_a_certificate_diagnostic(self):
        self.proxies = {'https': 'http://proxy.invalid:8080'}
        self.opener.open.side_effect = URLError(ssl.SSLCertVerificationError('private-cert-detail'))
        checks, _, _ = self.probe()
        self.assertIn('CA / sertifika', checks[0]['detail'])

    def test_failed_endpoint_does_not_hide_other_results_or_safe_ui_details(self):
        self.settings = replace(self.settings, npm_registry_url='https://npm.invalid/')
        self.opener.open.side_effect = [HTTPError(self.url, 403, 'private-reason', {}, None), self.response]
        checks, events, _ = self.probe()
        self.assertEqual([check['status'] for check in checks], ['missing', 'unverified'])
        state = ManagerState()
        for event in events:
            state.handle_event(event)
        self.assertIn('HTTP 403', state.report())
        self.assertIn('npm kilitli paket', state.report())
        self.assertNotIn('private-reason', state.report())

    def test_unknown_errors_have_safe_fallback_without_exception_data(self):
        self.opener.open.side_effect = RuntimeError('private-unexpected-detail')
        checks, events, _ = self.probe()
        self.assertEqual(checks[0]['status'], 'missing')
        self.assertNotIn('private-unexpected-detail', json.dumps(events))

    def test_cancellation_inside_request_is_not_converted_to_connection_failure(self):
        self.opener.open.side_effect = OperationCancelled('cancelled')
        events = []
        with patch('scripts.launcher.installation.source_settings', return_value=self.settings), \
             patch('urllib.request.build_opener', return_value=self.opener):
            worker.execute({'action': 'test-sources'}, events.append, lambda: None, threading.Event())
        self.assertTrue(events[-1].get('cancelled'), events)
        self.assertFalse(any(event['type'] == 'checks' for event in events))


if __name__ == '__main__':
    unittest.main()
