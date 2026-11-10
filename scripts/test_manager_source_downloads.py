"""End-to-end diagnostic stages run real parsers, streaming and digest checks."""
import base64
import hashlib
import json
import ssl
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from scripts.launcher.installation_sources import Artifact, SourceSettings
from scripts.launcher_test_support import create_project
from scripts.manager import source_checks, worker
from scripts.test_manager_source_probe import Response


class SourceDownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = create_project(self.root)
        self.wheel = b'complete wheel fixture'
        self.tarball = b'complete npm fixture'
        self.sha256 = hashlib.sha256(self.wheel).hexdigest()
        self.integrity = 'sha512-' + base64.b64encode(hashlib.sha512(self.tarball).digest()).decode('ascii')
        self.settings = SourceSettings(mode='corporate', python_index_url='https://python.invalid/simple',
                                       npm_registry_url='https://npm.invalid/repository/group')
        (self.project.frontend / 'package-lock.json').write_text(json.dumps({'packages': {
            'node_modules/@scope/demo': {'version': '1.2.3', 'integrity': self.integrity},
        }}))
        self.urls = []
        self.responses = {
            'https://python.invalid/simple/django/': Response(json.dumps({
                'name': 'django', 'files': [{'filename': 'django-5.2-py3-none-any.whl',
                'url': 'https://files.invalid/django.whl?token=private-token', 'hashes': {'sha256': self.sha256}}],
            }).encode(), url='https://python.invalid/simple/django/', headers={'Content-Type': 'application/vnd.pypi.simple.v1+json'}),
            'https://files.invalid/django.whl?token=private-token': Response(self.wheel),
            'https://npm.invalid/repository/group/@scope%2fdemo': Response(json.dumps({
                'name': '@scope/demo', 'versions': {'1.2.3': {'name': '@scope/demo', 'version': '1.2.3',
                'dist': {'tarball': 'https://files.invalid/demo.tgz'}}},
            }).encode(), url='https://npm.invalid/repository/group/@scope%2fdemo', headers={'Content-Type': 'application/json'}),
            'https://files.invalid/demo.tgz': Response(self.tarball, url='https://files.invalid/demo.tgz'),
        }
        self.opener = Mock()
        def open_url(request, **kwargs):
            self.urls.append(request.full_url)
            response = self.responses[request.full_url]
            if isinstance(response, Exception):
                raise response
            return response
        self.opener.open.side_effect = open_url

    def run_checks(self):
        with patch('urllib.request.build_opener', return_value=self.opener), \
             patch('urllib.request.getproxies', return_value={}):
            return source_checks._remote_checks(self.settings, self.project)

    def test_both_repositories_resolve_download_and_verify_locked_samples(self):
        events = []
        from dataclasses import replace
        self.settings = replace(self.settings, progress=events.append)
        checks = self.run_checks()
        self.assertEqual(len(self.urls), 4)
        self.assertEqual(len(checks), 8)
        self.assertTrue(all(row['status'] == 'ready' for row in checks), checks)
        self.assertIn('SHA512', checks[-1]['detail'])
        self.assertTrue(all(response.closed for response in self.responses.values()))
        self.assertNotIn('private-', json.dumps(checks) + json.dumps(events))
        self.assertIn('files.invalid', '\n'.join(events))

    def test_file_server_http403_is_attributed_to_download_and_npm_still_completes(self):
        self.responses['https://files.invalid/django.whl?token=private-token'] = HTTPError(
            'https://files.invalid/private', 403, 'private-reason', {}, None)
        checks = self.run_checks()
        failed = [row for row in checks if row['status'] == 'blocked']
        self.assertEqual(len(failed), 1)
        self.assertIn('Python', failed[0]['name'])
        self.assertIn('indirme', failed[0]['name'])
        self.assertIn('HTTP 403', failed[0]['detail'])
        self.assertTrue(all(row['status'] == 'ready' for row in checks if row['name'].startswith('npm')))
        self.assertNotIn('private-', json.dumps(checks))

    def test_hash_mismatch_is_reported_at_integrity_after_successful_full_download(self):
        self.responses['https://files.invalid/django.whl?token=private-token'] = Response(b'corrupt bytes')
        checks = self.run_checks()
        failed = next(row for row in checks if row['status'] == 'blocked')
        self.assertIn('bütünlüğü', failed['name'])
        self.assertIn('source_integrity_failed', failed['detail'])
        self.assertTrue(any('indirme' in row['name'] and row['status'] == 'ready' for row in checks))

    def test_runtime_is_fully_downloaded_and_verified_against_reviewed_catalog(self):
        artifact = Artifact('node', '1', 'node.zip', 'https://public.invalid/node.zip',
                            hashlib.sha256(b'archive').hexdigest(), 'zip', 'node.exe')
        self.settings = SourceSettings(mode='corporate', repository='https://runtime.invalid')
        self.responses['https://runtime.invalid/node.zip'] = Response(b'archive', url='https://runtime.invalid/node.zip')
        with patch('scripts.launcher.installation_sources.load_catalog', return_value={'node': artifact}):
            checks = self.run_checks()
        self.assertEqual(self.urls, ['https://runtime.invalid/node.zip'])
        self.assertEqual([row['status'] for row in checks], ['ready', 'ready'])
        self.assertIn('SHA256', checks[-1]['detail'])

    def test_runtime_runtimes_directory_fallback_retains_first404_in_trace(self):
        from dataclasses import replace
        events = []
        artifact = Artifact('node', '1', 'node.zip', 'https://public.invalid/node.zip',
                            hashlib.sha256(b'archive').hexdigest(), 'zip', 'node.exe')
        self.settings = replace(SourceSettings(mode='corporate', repository='https://runtime.invalid'), progress=events.append)
        self.responses['https://runtime.invalid/node.zip'] = HTTPError('https://runtime.invalid/node.zip', 404, '', {}, None)
        self.responses['https://runtime.invalid/runtimes/node.zip'] = Response(b'archive', url='https://runtime.invalid/runtimes/node.zip')
        with patch('scripts.launcher.installation_sources.load_catalog', return_value={'node': artifact}):
            checks = self.run_checks()
        self.assertTrue(all(row['status'] == 'ready' for row in checks), checks)
        self.assertIn('HTTP 404', '\n'.join(events))
        self.assertEqual(len(self.urls), 2)

    def test_runtime_http_rejections_try_permitted_runtimes_alternative(self):
        from dataclasses import replace
        artifact = Artifact('node', '1', 'node.zip', 'https://public.invalid/node.zip',
                            hashlib.sha256(b'archive').hexdigest(), 'zip', 'node.exe')
        root_url = 'https://runtime.invalid/node.zip'
        nested_url = 'https://runtime.invalid/runtimes/node.zip'
        for status in (400, 401, 403, 407, 429, 503):
            with self.subTest(status=status):
                events = []
                self.urls.clear()
                self.settings = replace(SourceSettings(mode='corporate', repository='https://runtime.invalid'),
                                        progress=events.append)
                self.responses[root_url] = HTTPError(root_url, status, 'private-reason', {}, None)
                self.responses[nested_url] = Response(b'archive', url=nested_url)
                with patch('scripts.launcher.installation_sources.load_catalog', return_value={'node': artifact}):
                    checks = self.run_checks()
                self.assertEqual(self.urls, [root_url, nested_url])
                self.assertEqual([row['status'] for row in checks], ['ready', 'ready'])
                self.assertIn(f'HTTP {status}', '\n'.join(events))
                self.assertNotIn('private-reason', json.dumps(checks) + json.dumps(events))

    def test_runtime_tls_and_hash_failures_do_not_try_an_alternative(self):
        artifact = Artifact('node', '1', 'node.zip', 'https://public.invalid/node.zip',
                            hashlib.sha256(b'archive').hexdigest(), 'zip', 'node.exe')
        root_url = 'https://runtime.invalid/node.zip'
        nested_url = 'https://runtime.invalid/runtimes/node.zip'
        self.settings = SourceSettings(mode='corporate', repository='https://runtime.invalid')
        cases = ((ssl.SSLCertVerificationError('private-reason'), 'source_tls_failed'),
                 (Response(b'corrupt archive', url=root_url), 'source_integrity_failed'))
        for response, expected_code in cases:
            with self.subTest(code=expected_code):
                self.urls.clear()
                self.responses[root_url] = response
                self.responses[nested_url] = Response(b'archive', url=nested_url)
                with patch('scripts.launcher.installation_sources.load_catalog', return_value={'node': artifact}):
                    checks = self.run_checks()
                self.assertEqual(self.urls, [root_url])
                failed = next(row for row in checks if row['status'] == 'blocked')
                self.assertIn(expected_code, failed['detail'])
                self.assertNotIn('private-reason', json.dumps(checks))

    def test_runtime_exhausted_alternatives_preserve_each_http_failure(self):
        from dataclasses import replace
        events = []
        artifact = Artifact('node', '1', 'node.zip', 'https://public.invalid/node.zip',
                            hashlib.sha256(b'archive').hexdigest(), 'zip', 'node.exe')
        root_url = 'https://runtime.invalid/node.zip'
        nested_url = 'https://runtime.invalid/runtimes/node.zip'
        self.settings = replace(SourceSettings(mode='corporate', repository='https://runtime.invalid'),
                                progress=events.append)
        self.responses[root_url] = HTTPError(root_url, 403, 'private-reason', {}, None)
        self.responses[nested_url] = HTTPError(nested_url, 404, 'private-reason', {}, None)
        with patch('scripts.launcher.installation_sources.load_catalog', return_value={'node': artifact}):
            checks = self.run_checks()
        self.assertEqual(self.urls, [root_url, nested_url])
        self.assertEqual([row['status'] for row in checks], ['blocked'])
        self.assertIn('HTTP 403', '\n'.join(events))
        self.assertIn('HTTP 404', checks[0]['detail'])
        self.assertNotIn('private-reason', json.dumps(checks) + json.dumps(events))

    def test_worker_cancellation_retains_completed_stage_and_stops_later_downloads(self):
        stop, events = threading.Event(), []
        original = self.responses['https://files.invalid/django.whl?token=private-token'].read1
        def cancelled_read(size):
            stop.set()
            return original(size)
        self.responses['https://files.invalid/django.whl?token=private-token'].read1 = cancelled_read
        with patch('urllib.request.build_opener', return_value=self.opener), \
             patch('urllib.request.getproxies', return_value={}):
            worker.execute({'action': 'test-sources', 'source_root': str(self.root), 'source_mode': 'corporate',
                            'python_index_url': self.settings.python_index_url,
                            'npm_registry_url': self.settings.npm_registry_url}, events.append, lambda: None, stop)
        checks = next(event['checks'] for event in events if event['type'] == 'checks')
        self.assertTrue(all(row['status'] == 'ready' for row in checks), checks)
        self.assertEqual(len(checks), 2)
        self.assertTrue(events[-1].get('cancelled'))
        self.assertEqual(len(self.urls), 2)


if __name__ == '__main__':
    unittest.main()
