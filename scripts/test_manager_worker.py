"""Headless desktop protocol regressions, with real private-pipe integration."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from scripts.manager import worker, transport
from scripts.launcher.installation_sources import SourceSettings


class WorkerProtocolTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Requires Windows pythonw and inherited native pipe handles')
    def test_windowed_python_restores_private_pipes_and_emits_utf8(self):
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        self.assertTrue(pythonw.is_file(), 'Native acceptance requires a full Python with pythonw.exe')
        child = subprocess.run([str(pythonw), '-m', 'scripts.manager.worker', '--manager-gate'],
                               input=b'go\n{"action":"invalid"}\n', capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 0)
        events = [json.loads(line) for line in child.stdout.splitlines()]
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        self.assertIn('İşlem', events[0]['message'])
        self.assertEqual(child.stderr, b'')

    def test_source_probe_ignores_unrelated_lifecycle_options(self):
        events = []
        worker.execute({'action': 'test-sources', 'source_root': str(Path.cwd()),
                        'source_mode': 'corporate', 'backend_port': 'bad port',
                        'tls_key_file': ['not used'], 'assets': ['not used']},
                       events.append, lambda: None, threading.Event())
        self.assertTrue(events[-1]['ok'], events)
        self.assertTrue(any(event['type'] == 'checks' for event in events))

    def test_lifecycle_start_ignores_unrelated_source_and_bundle_options(self):
        args = worker.arguments({'action': 'start', 'profile': 'dev', 'backend_port': 'unused',
                                 'repository': ['unused'], 'output': ['unused']})
        self.assertIsNone(args.repository)
        self.assertIsNone(args.output)
        self.assertIsNone(args.backend_port)

    def test_invalid_action_never_echoes_request_or_secret(self):
        events = []
        worker.execute({'action': 'invalid', 'password': 'never-echo-this'}, events.append,
                       lambda: None, threading.Event())
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        self.assertEqual(events[0]['type'], 'error')
        self.assertNotIn('never-echo-this', json.dumps(events))

    def test_offline_source_probe_makes_no_network_calls(self):
        events = []
        request = {'action': 'test-sources', 'source_mode': 'offline', 'source_root': str(Path.cwd())}
        with patch('urllib.request.build_opener') as network:
            worker.execute(request, events.append, lambda: None, threading.Event())
        network.assert_not_called()
        self.assertTrue(any(event['type'] == 'checks' for event in events))

    def test_private_pipe_rejects_invalid_request_without_console_trace(self):
        child = subprocess.run([sys.executable, '-m', 'scripts.manager.worker', '--manager-gate'],
                               input=b'go\n{"action":"invalid"}\n', capture_output=True, timeout=10)
        events = [json.loads(line) for line in child.stdout.splitlines()]
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        self.assertEqual(child.stderr, b'')

    def test_missing_gate_does_not_execute(self):
        child = subprocess.run([sys.executable, '-m', 'scripts.manager.worker', '--manager-gate'],
                               input=b'no\n', capture_output=True, timeout=10)
        self.assertNotEqual(child.returncode, 0)
        self.assertEqual(child.stdout, b'')

    def test_session_delivers_only_structured_events(self):
        events = []
        session = transport.WorkerSession(events.append)
        session.run({'action': 'invalid'})
        self.assertEqual(events[-1]['type'], 'done')
        self.assertFalse(events[-1]['ok'])
        self.assertFalse(session.running)

    def test_source_modes_do_not_inherit_saved_urls(self):
        request = worker.arguments({'profile': 'dev', 'source_mode': 'offline'})
        self.assertEqual(request.source_mode, 'offline')
        self.assertIsNone(request.python_index_url)
        self.assertFalse(request.use_saved_sources)

    def test_worker_exits_with_parent_pipe_still_open(self):
        child = subprocess.Popen([sys.executable, '-m', 'scripts.manager.worker', '--manager-gate'],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            child.stdin.write(b'go\n{"action":"invalid"}\n')
            child.stdin.flush()
            self.assertEqual(json.loads(child.stdout.readline())['type'], 'error')
            self.assertEqual(json.loads(child.stdout.readline())['type'], 'done')
            self.assertEqual(child.wait(timeout=5), 0)
            self.assertEqual(child.stderr.read(), b'')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()

    def test_worker_probes_python_while_control_pipe_read_is_pending(self):
        program = r'''
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch
from scripts.launcher import system_python
from scripts.manager import operations, worker

reading = threading.Event()
original_read = os.read
def observe_read(descriptor, size):
    if threading.current_thread() is not threading.main_thread():
        reading.set()
    return original_read(descriptor, size)

def dispatch(action, args, emit):
    if not reading.wait(2):
        raise AssertionError('Worker control reader did not start')
    # On Windows the inherited pipe's pending ReadFile blocks CPython stdin
    # initialization, even when its -c command never reads any input.
    time.sleep(0.1)
    emit({'type': 'phase', 'message': 'Checking system Python'})
    executable = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
    if system_python.discover_python(str(executable)) != executable:
        raise AssertionError('Unexpected system Python')
    emit({'type': 'status', 'message': 'System Python ready'})

with patch.object(worker.os, 'read', side_effect=observe_read), \
     patch.object(operations, '_dispatch', side_effect=dispatch), \
     patch.object(system_python, 'PROBE_TIMEOUT_SECONDS', 2):
    raise SystemExit(worker.main(['--manager-gate']))
'''
        child = subprocess.Popen([sys.executable, '-c', program], cwd=Path(__file__).resolve().parents[1],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            child.stdin.write(b'go\n{"action":"test-sources"}\n')
            child.stdin.flush()
            # Keep the owner side open: communicate() would close stdin and
            # release the pending read, hiding the Windows startup deadlock.
            self.assertEqual(child.wait(timeout=10), 0)
            events = [json.loads(line) for line in child.stdout]
            self.assertEqual(events, [
                {'type': 'phase', 'message': 'Checking system Python'},
                {'type': 'status', 'message': 'System Python ready'},
                {'type': 'done', 'ok': True},
            ])
            self.assertEqual(child.stderr.read(), b'')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()

    def test_corporate_probe_contacts_selected_endpoints_only(self):
        events = []
        settings = SourceSettings(mode='corporate', python_index_url='https://corporate.invalid/simple/',
                                  npm_registry_url='https://corporate.invalid/npm/')
        with patch('scripts.launcher.installation.source_settings', return_value=settings), \
             patch('urllib.request.build_opener') as factory:
            worker.execute({'action': 'test-sources'}, events.append, lambda: None, threading.Event())
        self.assertEqual([call.args[0] for call in factory.return_value.open.call_args_list],
                         [settings.python_index_url, settings.npm_registry_url])

    def test_corporate_local_package_is_a_valid_source_without_urls(self):
        events = []
        settings = SourceSettings(mode='corporate', repository=Path('/selected/packages'))
        with patch('scripts.launcher.installation.source_settings', return_value=settings), \
             patch('scripts.launcher.installation_dependencies._offline_dependencies', return_value=Path('/selected/packages')), \
             patch('urllib.request.build_opener') as network:
            worker.execute({'action': 'test-sources', 'source_root': str(Path.cwd())},
                           events.append, lambda: None, threading.Event())
        checks = next(event['checks'] for event in events if event['type'] == 'checks')
        self.assertTrue(any(check['status'] == 'ready' for check in checks))
        network.return_value.open.assert_not_called()

    def test_failure_reason_never_includes_exception_payload(self):
        code, reason = worker._failure_reason(worker.LauncherError('password=never-echo TLS error'))
        self.assertEqual(code, 'tls_failed')
        self.assertNotIn('never-echo', reason)


if __name__ == '__main__':
    unittest.main()
