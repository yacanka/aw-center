"""Python acquisition failures retain safe evidence after source fallback."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.launcher import installation_bundle as bundle
from scripts.launcher import installation_dependencies as dependencies
from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher_test_support import create_project
from scripts.manager import worker


class PythonSourceFailureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = create_project(self.root)

    def run_acquisition(self, operation, diagnostics, *, mode='restricted'):
        events, indexes = [], []
        results = iter(diagnostics)

        def capture(command, *args, **kwargs):
            indexes.append(command[command.index('--index-url') + 1])
            return subprocess.CompletedProcess(command, 1, '', next(results))

        settings = SourceSettings(mode=mode, python_index_url='https://selected.invalid/simple',
                                  progress=events.append)
        if operation == 'install':
            module, attribute = dependencies, 'capture'
        else:
            module, attribute = bundle, '_capture'
        with patch.object(module, attribute, side_effect=capture):
            try:
                if operation == 'install':
                    dependencies._python_packages(self.project, settings, {}, self.root)
                else:
                    bundle._acquire_wheels(self.project, self.root / 'output', settings, {})
            except dependencies.LauncherError as error:
                return error, events, indexes
        self.fail('Unavailable package sources must fail acquisition')

    def test_exhausted_sources_keep_http_status_and_safe_remedy(self):
        diagnostic = ('ERROR: Could not install packages due to an HTTPError: '
                      '403 Client Error: Forbidden for url: '
                      'https://synthetic-user:synthetic-secret@private.invalid/file.whl?token=private-token')
        for operation in ('install', 'bundle'):
            with self.subTest(operation=operation):
                error, events, indexes = self.run_acquisition(operation, [diagnostic], mode='corporate')
                self.assertIsInstance(error, dependencies.PackageCommandError)
                self.assertEqual(error.code, 'package_source_http_rejected')
                self.assertIn('HTTP 403', str(error))
                self.assertIn('erişim', error.remedy)
                self.assertEqual(indexes, ['https://selected.invalid/simple'])
                rendered = str(error) + error.remedy + json.dumps(events)
                for private in ('synthetic-', 'private.invalid', 'private-token', 'file.whl'):
                    self.assertNotIn(private, rendered)
                self.assertFalse(any('sıradaki izinli kaynak' in event for event in events))

    def test_every_failed_attempt_is_reported_before_last_failure_is_raised(self):
        for operation in ('install', 'bundle'):
            with self.subTest(operation=operation):
                error, events, indexes = self.run_acquisition(operation, [
                    'ProxyError: Tunnel connection failed: 407 Proxy Authentication Required',
                    'ReadTimeoutError: private-timeout-detail',
                ])
                self.assertEqual(indexes, ['https://selected.invalid/simple', 'https://pypi.org/simple'])
                self.assertEqual(getattr(error, 'code', None), 'package_source_timeout')
                self.assertIn('zaman aşımı', str(error))
                self.assertTrue(any('HTTP 407' in event for event in events))
                self.assertIn('Proxy', '\n'.join(events))
                self.assertNotIn('private-timeout-detail', json.dumps(events))

    def test_transport_failures_are_distinguished_without_raw_diagnostics(self):
        cases = (
            ('NameResolutionError: private-detail', 'package_source_dns_failed', 'DNS'),
            ('NewConnectionError: connection refused private-detail',
             'package_source_connection_failed', 'bağlantı'),
            ('HTTP error 404 private-detail', 'package_source_http_rejected', 'HTTP 404'),
            ('503 Service Unavailable private-detail', 'package_source_http_rejected', 'HTTP 503'),
            ('502 Bad Gateway private-detail', 'package_source_http_rejected', 'HTTP 502'),
            ('504 Gateway Timeout private-detail', 'package_source_http_rejected', 'HTTP 504'),
        )
        for number, (diagnostic, code, detail) in enumerate(cases):
            with self.subTest(diagnostic=diagnostic):
                # Each installation acquisition owns a fresh temporary stage.
                stage = self.root / str(number)
                stage.mkdir()
                events = []
                settings = SourceSettings(mode='corporate', python_index_url='https://selected.invalid/simple',
                                          progress=events.append)
                with patch.object(dependencies, 'capture', return_value=
                                  subprocess.CompletedProcess([], 1, '', diagnostic)):
                    with self.assertRaises(dependencies.LauncherError) as caught:
                        dependencies._python_packages(self.project, settings, {}, stage)
                self.assertEqual(getattr(caught.exception, 'code', None), code)
                self.assertIn(detail, str(caught.exception))
                self.assertNotIn('private-detail', str(caught.exception) + json.dumps(events))

    def test_manager_preserves_source_failure_code_and_remedy(self):
        events = []

        def dispatch(action, args, emit):
            dependencies._python_packages(self.project, SourceSettings(mode='corporate',
                python_index_url='https://selected.invalid/simple', progress=args.progress), {}, self.root)

        with patch('scripts.manager.operations._dispatch', side_effect=dispatch), \
             patch.object(dependencies, 'capture', return_value=
                          subprocess.CompletedProcess([], 1, '', 'HTTP error 403 private-detail')):
            worker.execute({'action': 'provision'}, events.append, lambda: None, threading.Event())
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'package_source_http_rejected')
        self.assertIn('HTTP 403', error['message'])
        self.assertIn('erişim', error['remedy'])
        self.assertNotIn('private-detail', json.dumps(events))
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})


if __name__ == '__main__':
    unittest.main()
