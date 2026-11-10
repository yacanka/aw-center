"""Real streaming and integrity checks with only the external HTTP boundary faked."""
import hashlib
import io
import errno
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from scripts.launcher.process import OperationCancelled, operation_control
from scripts.manager import source_probe as probe


class Response(io.BytesIO):
    def __init__(self, body=b'wheel bytes', *, url='https://files.invalid/file.whl',
                 status=200, headers=None):
        super().__init__(body)
        self.status, self.url = status, url
        self.headers = {'Content-Length': str(len(body)), **(headers or {})}

    def geturl(self):
        return self.url


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.opener = Mock()
        self.client = probe.ProbeClient(self.opener, {}, self.events.append)

    def test_download_reads_all_bytes_and_verifies_strong_hash_without_retaining_files(self):
        body = b'fixture' * 30000
        response = Response(body)
        self.opener.open.return_value = response
        created = []
        temporary_directory = tempfile.TemporaryDirectory
        def temporary(*args, **kwargs):
            result = temporary_directory(*args, **kwargs)
            created.append(Path(result.name))
            return result
        with patch.object(probe.tempfile, 'TemporaryDirectory', side_effect=temporary):
            result = self.client.download(response.url)
        probe.verify_digest(result, {'sha256': (hashlib.sha256(body).hexdigest(),)})
        self.assertEqual(result.size, len(body))
        self.assertIsNone(result.body)
        self.assertTrue(response.closed)
        self.assertTrue(created)
        self.assertTrue(all(not path.exists() for path in created))
        request = self.opener.open.call_args.args[0]
        self.assertIsInstance(request, Request)
        self.assertEqual(request.full_url, response.url)

    def test_metadata_returns_real_body_and_final_https_address(self):
        response = Response(b'{"versions": {}}', url='https://repo.invalid/final/')
        self.opener.open.return_value = response
        result = self.client.metadata('https://repo.invalid/start/', accept='application/json')
        self.assertEqual(result.body, b'{"versions": {}}')
        self.assertEqual(result.url, response.url)
        self.assertTrue(response.closed)

    def test_temporary_storage_failures_are_not_reported_as_repository_connection_errors(self):
        for error, code in ((PermissionError(errno.EACCES, 'private-path'), 'source_storage_access_denied'),
                            (OSError(errno.ENOSPC, 'private-path'), 'source_storage_full')):
            with self.subTest(code=code):
                self.opener.open.return_value = Response()
                with patch.object(probe.Path, 'open', side_effect=error):
                    with self.assertRaises(probe.ProbeFailure) as caught:
                        self.client.download('https://files.invalid/file.whl')
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn('private-', str(caught.exception))

    def test_buffered_close_and_temporary_cleanup_errors_keep_storage_diagnostic(self):
        for boundary in ('file', 'directory'):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as owned:
                self.opener.open.return_value = Response()
                manager = Mock()
                manager.__enter__ = Mock(return_value=io.BytesIO() if boundary == 'file' else owned)
                manager.__exit__ = Mock(side_effect=OSError(errno.ENOSPC, 'private-path'))
                target = 'open' if boundary == 'file' else 'TemporaryDirectory'
                owner = probe.Path if boundary == 'file' else probe.tempfile
                with patch.object(owner, target, return_value=manager):
                    with self.assertRaises(probe.ProbeFailure) as caught:
                        self.client.download('https://files.invalid/file.whl')
                self.assertEqual(caught.exception.code, 'source_storage_full')
                self.assertNotIn('private-', str(caught.exception))

    def test_declared_and_streamed_size_limits_reject_before_accepting_artifact(self):
        for headers in ({'Content-Length': '100'}, {'Content-Length': ''}):
            with self.subTest(headers=headers):
                response = Response(b'12345', headers=headers)
                self.opener.open.return_value = response
                with self.assertRaises(probe.ProbeFailure) as caught:
                    self.client.download(response.url, limit=4)
                self.assertEqual(caught.exception.code, 'source_size_limit')
                self.assertTrue(response.closed)

    def test_truncated_and_empty_artifacts_fail_instead_of_verifying(self):
        for body, headers in ((b'12', {'Content-Length': '3'}), (b'', {})):
            with self.subTest(body=body):
                response = Response(body, headers=headers)
                self.opener.open.return_value = response
                with self.assertRaises(probe.ProbeFailure) as caught:
                    self.client.download(response.url)
                self.assertEqual(caught.exception.code, 'source_incomplete_download')
                self.assertTrue(response.closed)

    def test_hash_mismatch_and_missing_expected_hash_never_pass(self):
        self.opener.open.return_value = Response()
        result = self.client.download('https://files.invalid/file.whl')
        for expected, code in (({'sha256': ('0' * 64,)}, 'source_integrity_failed'),
                               ({}, 'source_hash_missing')):
            with self.subTest(code=code), self.assertRaises(probe.ProbeFailure) as caught:
                probe.verify_digest(result, expected)
            self.assertEqual(caught.exception.code, code)

    def test_transport_failures_keep_reviewed_reason_without_private_payload(self):
        cases = (
            (URLError(socket.gaierror('private-detail')), 'source_dns_failed', 'DNS'),
            (URLError(TimeoutError('private-detail')), 'source_timeout', 'zaman aşımı'),
            (ssl.SSLCertVerificationError('private-detail'), 'source_tls_failed', 'sertifika'),
            (ssl.SSLError('private-detail'), 'source_tls_failed', 'TLS'),
            (ConnectionRefusedError('private-detail'), 'source_connection_failed', 'Bağlantı'),
            (URLError(OSError('Tunnel connection failed: 407 private-detail')),
             'source_http_407', 'Proxy'),
        )
        for error, code, detail in cases:
            with self.subTest(code=code):
                self.opener.open.side_effect = error
                with self.assertRaises(probe.ProbeFailure) as caught:
                    self.client.download('https://files.invalid/file.whl?token=private-token')
                self.assertEqual(caught.exception.code, code)
                self.assertIn(detail, str(caught.exception))
                self.assertNotIn('private-', str(caught.exception) + '\n'.join(self.events))

    def test_transport_failure_uses_proxy_route_of_last_redirect_target(self):
        client = probe.ProbeClient(self.opener, {'https': 'http://proxy.invalid'}, self.events.append)
        def redirected_failure(request, **kwargs):
            request._source_trace['url'] = 'https://proxied.invalid/file'
            raise TimeoutError('private-detail')
        self.opener.open.side_effect = redirected_failure
        with patch('urllib.request.proxy_bypass', side_effect=lambda host: host == 'bypass.invalid'):
            with self.assertRaises(probe.ProbeFailure) as caught:
                client.download('https://bypass.invalid/file')
        self.assertIn('Proxy adresini', str(caught.exception))
        self.assertNotIn('private-', str(caught.exception))

    def test_http_errors_close_response_body_and_report_status_and_remedy(self):
        for status, detail in ((400, 'adres'), (401, 'kimlik'), (403, 'erişim'),
                               (404, 'bulunamadı'), (407, 'Proxy'), (503, 'sunucu')):
            with self.subTest(status=status):
                body = io.BytesIO(b'private-body')
                self.opener.open.side_effect = HTTPError('https://files.invalid/private', status,
                                                         'private-reason', {}, body)
                with self.assertRaises(probe.ProbeFailure) as caught:
                    self.client.download('https://files.invalid/file.whl')
                self.assertIn(f'HTTP {status}', str(caught.exception))
                self.assertIn(detail, str(caught.exception))
                self.assertNotIn('private-', str(caught.exception))
                self.assertTrue(body.closed)

    def test_deadline_is_checked_during_streaming(self):
        response = Response()
        self.opener.open.return_value = response
        with patch.object(probe.time, 'monotonic', side_effect=[0, 0, 0, 121, 121]):
            with self.assertRaises(probe.ProbeFailure) as caught:
                self.client.download(response.url)
        self.assertEqual(caught.exception.code, 'source_timeout')
        self.assertTrue(response.closed)

    def test_cancellation_stops_streaming_and_closes_response(self):
        stop = threading.Event()
        response = Response(b'abc')
        original_read = response.read1
        def read(size):
            stop.set()
            return original_read(size)
        response.read1 = read
        self.opener.open.return_value = response
        with operation_control(stop), self.assertRaises(OperationCancelled):
            self.client.download(response.url)
        self.assertTrue(response.closed)

    def test_https_and_credential_policy_applies_to_file_urls_and_redirects(self):
        invalid = ('http://files.invalid/file', 'https://user:private-secret@files.invalid/file')
        handler = probe.ProbeRedirect(self.events.append)
        request = Request('https://repo.invalid/file')
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(probe.ProbeFailure):
                self.client.download(url)
            with self.subTest(redirect=url), self.assertRaises(probe.ProbeFailure):
                handler.redirect_request(request, None, 302, 'Found', {}, url)
        self.opener.open.assert_not_called()
        self.assertNotIn('private-', '\n'.join(self.events))

    def test_redirect_trace_does_not_expose_signed_query_or_credentials(self):
        handler = probe.ProbeRedirect(self.events.append)
        request = Request('https://repo.invalid/file')
        redirected = handler.redirect_request(request, None, 302, 'Found', {},
                                             'https://cdn.invalid/file?token=private-token')
        self.assertEqual(redirected.host, 'cdn.invalid')
        self.assertIn('cdn.invalid', '\n'.join(self.events))
        self.assertNotIn('private-', '\n'.join(self.events))


class RedirectTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.handler = probe.ProbeRedirect(self.events.append)
        self.handler.parent = Mock()

    def request(self):
        request = Request('https://repo.invalid/file')
        request.timeout = 10
        return request

    def test_redirect_closes_body_without_reading_unbounded_redirect_payload(self):
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                body = Response(b'large redirect body')
                body.read = Mock(side_effect=AssertionError('Redirect body must not be drained'))
                result = getattr(self.handler, 'http_error_' + str(code))(
                    self.request(), body, code, 'Found', {'location': 'https://cdn.invalid/file'})
                self.assertIs(result, self.handler.parent.open.return_value)
                self.assertTrue(body.closed)

    def test_rejected_or_cancelled_redirect_always_closes_original_response(self):
        body = Response()
        with self.assertRaises(probe.ProbeFailure):
            self.handler.http_error_302(self.request(), body, 302, 'Found',
                                        {'location': 'http://unsafe.invalid/file'})
        self.assertTrue(body.closed)
        stop = threading.Event()
        stop.set()
        body = Response()
        with operation_control(stop), self.assertRaises(OperationCancelled):
            self.handler.http_error_302(self.request(), body, 302, 'Found',
                                        {'location': 'https://cdn.invalid/file'})
        self.assertTrue(body.closed)

    def test_proxy_and_origin_credentials_are_not_copied_to_redirect_target(self):
        request = self.request()
        request.add_header('Proxy-Authorization', 'Basic private-proxy')
        request.add_header('Authorization', 'Bearer private-origin')
        request.add_unredirected_header('Authorization', 'Bearer private-unredirected')
        self.handler.http_error_302(request, Response(), 302, 'Found', {'location': 'https://bypass.invalid/file'})
        redirected = self.handler.parent.open.call_args.args[0]
        headers = {key.lower(): value for key, value in redirected.header_items()}
        self.assertNotIn('authorization', headers)
        self.assertNotIn('proxy-authorization', headers)
        self.assertNotIn('private-', '\n'.join(self.events))

    def test_each_redirect_reports_its_actual_proxy_bypass_route(self):
        handler = probe.ProbeRedirect(self.events.append, {'https': 'http://user:private-proxy@proxy.invalid'})
        handler.parent = Mock()
        with patch('urllib.request.proxy_bypass', side_effect=lambda host: host == 'bypass.invalid'):
            handler.http_error_302(self.request(), Response(), 302, 'Found', {'location': 'https://bypass.invalid/file'})
            handler.http_error_302(self.request(), Response(), 302, 'Found', {'location': 'https://proxied.invalid/file'})
        self.assertIn('proxy bypass', self.events[0])
        self.assertIn('kurumsal proxy', self.events[1])
        self.assertNotIn('private-', '\n'.join(self.events))

    def test_redirect_chain_shares_deadline_and_rejects_sixth_hop(self):
        request = self.request()
        request._source_trace = {'url': request.full_url, 'hops': 0, 'deadline': 100}
        with patch.object(probe.time, 'monotonic', return_value=95):
            for number in range(5):
                self.handler.http_error_302(request, Response(), 302, 'Found',
                                            {'location': f'https://cdn.invalid/file{number}'})
                request = self.handler.parent.open.call_args.args[0]
                self.assertEqual(self.handler.parent.open.call_args.kwargs['timeout'], 5)
        body = Response()
        with self.assertRaises(probe.ProbeFailure) as caught:
            self.handler.http_error_302(request, body, 302, 'Found', {'location': 'https://cdn.invalid/sixth'})
        self.assertEqual(caught.exception.code, 'source_redirect_limit')
        self.assertTrue(body.closed)

    def test_redirect_timeout_uses_remaining_transfer_budget(self):
        request = self.request()
        request._source_trace = {'url': request.full_url, 'hops': 0, 'deadline': 100}
        body = Response()
        with patch.object(probe.time, 'monotonic', return_value=101), self.assertRaises(probe.ProbeFailure) as caught:
            self.handler.http_error_302(request, body, 302, 'Found', {'location': 'https://cdn.invalid/file'})
        self.assertEqual(caught.exception.code, 'source_timeout')
        self.handler.parent.open.assert_not_called()
        self.assertTrue(body.closed)


if __name__ == '__main__':
    unittest.main()
