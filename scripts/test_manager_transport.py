"""Worker sessions keep slow private pipes off the desktop event thread."""
import json
import queue
import subprocess
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from scripts.manager import transport


_POPEN = subprocess.Popen
_WAITING_WORKER = r'''
import json, sys, time
if sys.stdin.buffer.readline() != b'go\n':
    raise SystemExit(2)
request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({'type': 'phase', 'message': 'waiting'}), flush=True)
while True:
    line = sys.stdin.buffer.readline()
    if not line:
        break
    message = json.loads(line)
    if message.get('type') == 'cancel':
        time.sleep(request.get('finish_delay', 0))
        print(json.dumps({'type': 'done', 'ok': True, 'cancelled': True}), flush=True)
        break
'''


class _PrivateInput:
    """Keep real process/pipe lifecycle, replacing only a stalled OS write."""

    def __init__(self, stream, *, blocked=False, partial=False, broken=False):
        self.stream = stream
        self.blocked = blocked
        self.partial = partial
        self.broken = broken
        self.entered = threading.Event()
        self.release = threading.Event()
        self.writes = []

    @property
    def closed(self):
        return self.stream.closed

    def write(self, value):
        value = bytes(value)
        self.writes.append(value)
        if self.blocked and b'"type": "admin"' in value:
            self.entered.set()
            self.release.wait()
        if self.broken:
            raise BrokenPipeError('private failure detail')
        return self.stream.write(value[:3] if self.partial else value)

    def flush(self):
        return self.stream.flush()

    def close(self):
        self.stream.close()


class WorkerTransportTests(unittest.TestCase):
    def setUp(self):
        self.children = []
        self.threads = []
        self.inputs = []

    def tearDown(self):
        for stream in self.inputs:
            stream.release.set()
        for child in self.children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            for stream in (child.stdin, child.stdout):
                if stream is not None and not stream.closed:
                    stream.close()
        for thread in self.threads:
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive(), 'desktop task or callback was not released')

    def _spawn_worker(self, *, program=_WAITING_WORKER, blocked=False, partial=False, broken=False):
        def spawn(command, **options):
            child = _POPEN([sys.executable, '-u', '-c', program], **options)
            child.stdin = _PrivateInput(child.stdin, blocked=blocked, partial=partial, broken=broken)
            self.children.append(child)
            self.inputs.append(child.stdin)
            return child
        return spawn

    def _start(self, session, request=None):
        thread = threading.Thread(target=session.run, args=(request or {'action': 'test-sources'},), daemon=True)
        self.threads.append(thread)
        thread.start()
        return thread

    def _prompt_callback(self, callback):
        finished = threading.Event()
        errors = []
        def invoke():
            try:
                callback()
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()
        thread = threading.Thread(target=invoke, name='simulated-tk-callback', daemon=True)
        self.threads.append(thread)
        thread.start()
        self.assertTrue(finished.wait(0.5), 'desktop callback waited for the worker pipe')
        if errors:
            raise errors[0]

    def _wait_phase(self, events):
        event = events.get(timeout=5)
        self.assertEqual(event['type'], 'phase')

    def test_send_and_stop_return_while_private_input_is_blocked(self):
        events = queue.Queue()
        session = transport.WorkerSession(events.put)
        with patch.object(transport.subprocess, 'Popen', side_effect=self._spawn_worker(blocked=True)):
            runner = self._start(session)
            self._wait_phase(events)
            self._prompt_callback(lambda: session.send({'type': 'admin', 'value': 'private-value'}))
            self.assertTrue(self.inputs[0].entered.wait(2))
            self._prompt_callback(session.stop)
            # A pipe that never resumes must not prevent session finalization.
            runner.join(timeout=5)
            self.assertFalse(runner.is_alive(), 'stalled input prevented worker cleanup')
        self.assertIsNotNone(self.children[0].poll())
        self.assertTrue(self.children[0].stdin.closed)
        self.assertFalse(session.running)
        self.assertEqual(list(events.queue)[-1]['type'], 'done')

    def test_outbound_capacity_failure_is_visible_without_blocking(self):
        events = queue.Queue()
        session = transport.WorkerSession(events.put)
        with patch.object(transport.subprocess, 'Popen', side_effect=self._spawn_worker(blocked=True)):
            self._start(session)
            self._wait_phase(events)
            self._prompt_callback(lambda: session.send({'type': 'admin', 'value': 'first'}))
            self.assertTrue(self.inputs[0].entered.wait(2))
            started = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, 'queue'):
                for _ in range(100):
                    session.send({'type': 'admin', 'value': 'private-value'})
            self.assertLess(time.monotonic() - started, 0.5)
            self._prompt_callback(session.stop)

    def test_cancel_precedes_controls_waiting_behind_an_active_write(self):
        events = queue.Queue()
        session = transport.WorkerSession(events.put)
        with patch.object(transport.subprocess, 'Popen', side_effect=self._spawn_worker(blocked=True)):
            runner = self._start(session)
            self._wait_phase(events)
            self._prompt_callback(lambda: session.send({'type': 'admin', 'value': 'active'}))
            self.assertTrue(self.inputs[0].entered.wait(2))
            session.send({'type': 'admin', 'value': 'queued'})
            self._prompt_callback(session.stop)
            self.inputs[0].release.set()
            runner.join(timeout=5)
        self.assertFalse(runner.is_alive())
        controls = [json.loads(value) for value in self.inputs[0].writes[2:]]
        self.assertEqual(controls, [{'type': 'admin', 'value': 'active'}, {'type': 'cancel'}])
        self.assertEqual(list(events.queue)[-1], {'type': 'done', 'ok': True, 'cancelled': True})

    def test_cancel_during_spawn_is_retained_after_gate_assignment(self):
        events = queue.Queue()
        spawning, release = threading.Event(), threading.Event()
        spawn = self._spawn_worker()
        def delayed_spawn(command, **options):
            spawning.set()
            release.wait(timeout=3)
            return spawn(command, **options)
        session = transport.WorkerSession(events.put)
        try:
            with patch.object(transport.subprocess, 'Popen', side_effect=delayed_spawn):
                runner = self._start(session)
                self.assertTrue(spawning.wait(2))
                self._prompt_callback(session.stop)
                release.set()
                runner.join(timeout=5)
            self.assertFalse(runner.is_alive())
            self.assertEqual(list(events.queue)[-1], {'type': 'done', 'ok': True, 'cancelled': True})
            self.assertEqual(self.inputs[0].writes[0], b'go\n')
        finally:
            release.set()

    def test_delivered_cancel_waits_for_worker_safe_boundary(self):
        events = queue.Queue()
        session = transport.WorkerSession(events.put)
        with patch.object(transport.subprocess, 'Popen', side_effect=self._spawn_worker()), \
             patch.object(transport, 'CANCEL_DELIVERY_TIMEOUT', 0.2):
            runner = self._start(session, {'action': 'test-sources', 'finish_delay': 0.6})
            self._wait_phase(events)
            session.stop()
            runner.join(timeout=5)
        self.assertFalse(runner.is_alive())
        self.assertEqual(list(events.queue)[-1], {'type': 'done', 'ok': True, 'cancelled': True})

    def test_partial_raw_writes_deliver_complete_messages(self):
        events = queue.Queue()
        session = transport.WorkerSession(events.put)
        with patch.object(transport.subprocess, 'Popen', side_effect=self._spawn_worker(partial=True)):
            runner = self._start(session)
            self._wait_phase(events)
            session.stop()
            runner.join(timeout=5)
        self.assertFalse(runner.is_alive())
        self.assertEqual(list(events.queue)[-1], {'type': 'done', 'ok': True, 'cancelled': True})

    def test_broken_input_reaps_worker_and_reports_sanitized_failure(self):
        events = []
        session = transport.WorkerSession(events.append)
        with patch.object(transport.subprocess, 'Popen', side_effect=self._spawn_worker(broken=True)):
            runner = self._start(session)
            runner.join(timeout=5)
        self.assertFalse(runner.is_alive())
        self.assertIsNotNone(self.children[0].poll())
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        self.assertNotIn('private failure detail', json.dumps(events))

    def test_containment_failure_never_opens_the_worker_gate(self):
        events = []
        spawn = self._spawn_worker()
        def windows_spawn(command, **options):
            options.pop('creationflags', None)
            child = spawn(command, **options)
            child._handle = object()
            return child
        with patch.object(transport, 'os', types.SimpleNamespace(name='nt')), \
             patch.object(transport.subprocess, 'CREATE_NO_WINDOW', 0, create=True), \
             patch.object(transport.subprocess, 'Popen', side_effect=windows_spawn), \
             patch('scripts.launcher.windows_job.WindowsJob', side_effect=OSError('containment failed')):
            transport.WorkerSession(events.append).run({'action': 'invalid'})
        self.assertEqual(self.inputs[0].writes, [])
        self.assertIsNotNone(self.children[0].poll())
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        self.assertEqual(events[-2]['code'], 'worker_containment_failed')

    def test_start_denied_reports_only_safe_stage_and_system_code(self):
        events = []
        with patch.object(transport.subprocess, 'Popen', side_effect=PermissionError(13, 'private-start-secret')):
            transport.WorkerSession(events.append).run({'action': 'test-sources'})
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        self.assertEqual(events[-2]['code'], 'worker_start_denied')
        self.assertIn('13', events[-2]['message'])
        self.assertNotIn('private-start-secret', json.dumps(events))

    def test_worker_exit_without_result_reports_exit_code_without_raw_output(self):
        events = []
        program = "import sys; sys.stdin.buffer.readline(); sys.stdin.buffer.readline(); sys.exit(7)"
        with patch.object(transport.subprocess, 'Popen', side_effect=self._spawn_worker(program=program)):
            transport.WorkerSession(events.append).run({'action': 'test-sources'})
        self.assertEqual(events[-2]['code'], 'worker_exited')
        self.assertIn('7', events[-2]['message'])
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})

    def test_blocked_session_does_not_delay_an_independent_real_worker(self):
        events = queue.Queue()
        slow = transport.WorkerSession(events.put)
        spawn = self._spawn_worker(blocked=True)
        def selected_spawn(command, **options):
            if not self.children:
                return spawn(command, **options)
            child = _POPEN(command, **options)
            self.children.append(child)
            return child
        with patch.object(transport.subprocess, 'Popen', side_effect=selected_spawn):
            self._start(slow)
            self._wait_phase(events)
            self._prompt_callback(lambda: slow.send({'type': 'admin', 'value': 'private-value'}))
            self.assertTrue(self.inputs[0].entered.wait(2))
            independent_events = []
            independent = transport.WorkerSession(independent_events.append)
            runner = self._start(independent, {'action': 'invalid'})
            runner.join(timeout=5)
            self.assertFalse(runner.is_alive())
            self.assertEqual(independent_events[-1], {'type': 'done', 'ok': False})
            self._prompt_callback(slow.stop)

    def test_full_os_pipe_does_not_delay_other_workers_or_cleanup(self):
        program = ('import sys, time\n'
                   'sys.stdin.buffer.readline()\n'
                   'sys.stdin.buffer.readline()\n'
                   'print(\'{"type":"phase","message":"waiting"}\', flush=True)\n'
                   'time.sleep(60)\n')
        events = queue.Queue()
        slow = transport.WorkerSession(events.put)
        spawn = self._spawn_worker(program=program)
        def selected_spawn(command, **options):
            if not self.children:
                return spawn(command, **options)
            child = _POPEN(command, **options)
            self.children.append(child)
            return child
        with patch.object(transport.subprocess, 'Popen', side_effect=selected_spawn):
            slow_runner = self._start(slow)
            self._wait_phase(events)
            with self.assertRaisesRegex(RuntimeError, 'queue'):
                for _ in range(100):
                    slow.send({'type': 'admin', 'value': 'x' * 60000})
            independent_events = []
            independent = transport.WorkerSession(independent_events.append)
            runner = self._start(independent, {'action': 'invalid'})
            runner.join(timeout=5)
            self.assertFalse(runner.is_alive())
            self.assertEqual(independent_events[-1], {'type': 'done', 'ok': False})
            self._prompt_callback(slow.stop)
            slow_runner.join(timeout=5)
        self.assertFalse(slow_runner.is_alive())
        self.assertIsNotNone(self.children[0].poll())
        self.assertEqual(list(events.queue)[-1], {'type': 'done', 'ok': False})

    def test_real_invalid_request_keeps_credentials_inside_private_stdin(self):
        events, commands = [], []
        def spawn(command, **options):
            commands.append((command, options.get('env')))
            child = _POPEN(command, **options)
            self.children.append(child)
            return child
        session = transport.WorkerSession(events.append)
        with patch.object(transport.subprocess, 'Popen', side_effect=spawn):
            session.run({'action': 'invalid', 'password': 'transport-private-test-marker'})
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        self.assertNotIn('transport-private-test-marker', json.dumps(commands))
        self.assertNotIn('transport-private-test-marker', json.dumps(events))
        self.assertIsNotNone(self.children[0].poll())
        self.assertTrue(self.children[0].stdin.closed)
        self.assertTrue(self.children[0].stdout.closed)

    def test_invalid_or_incomplete_stdout_is_rejected_and_reaped(self):
        responses = [b'[1]\n', b'{"type":"unknown"}\n', b'not-json\n',
                     b'x' * (64 * 1024 + 1), b'{"type":"phase","message":"waiting"}\n']
        for response in responses:
            with self.subTest(response=response[:20]):
                program = ('import sys\n'
                           'sys.stdin.buffer.readline()\n'
                           'sys.stdin.buffer.readline()\n'
                           f'sys.stdout.buffer.write({response!r})\n'
                           'sys.stdout.buffer.flush()\n')
                events = []
                with patch.object(transport.subprocess, 'Popen',
                                  side_effect=self._spawn_worker(program=program)):
                    transport.WorkerSession(events.append).run({'action': 'invalid'})
                self.assertEqual(events[-1], {'type': 'done', 'ok': False})
                self.assertEqual(events[-2]['type'], 'error')
                self.assertIsNotNone(self.children[-1].poll())

    def test_events_after_done_are_never_forwarded(self):
        program = ('import sys\n'
                   'sys.stdin.buffer.readline()\n'
                   'sys.stdin.buffer.readline()\n'
                   'print(\'{"type":"done","ok":true}\', flush=True)\n'
                   'print(\'{"type":"status","message":"late"}\', flush=True)\n')
        events = []
        with patch.object(transport.subprocess, 'Popen', side_effect=self._spawn_worker(program=program)):
            session = transport.WorkerSession(events.append)
            session.run({'action': 'invalid'})
        self.assertEqual(events, [{'type': 'done', 'ok': True}])
        self.assertIsNotNone(self.children[0].poll())
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            session.send({'type': 'admin', 'value': 'late-value'})

    def test_real_corporate_probe_has_no_implicit_public_endpoints(self):
        events = []
        session = transport.WorkerSession(events.append)
        session.run({'action': 'test-sources', 'source_mode': 'corporate'})
        self.assertEqual(events[-1], {'type': 'done', 'ok': True})
        checks = next(event['checks'] for event in events if event['type'] == 'checks')
        self.assertEqual([check['name'] for check in checks], ['Kaynaklar'])
        self.assertFalse(session.running)

    def test_real_worker_protocol_is_utf8_with_legacy_windows_pipe_encoding(self):
        events = []
        # Windows pipes can inherit the system ANSI code page. The IPC wire
        # format must remain UTF-8 even when operator-visible checks are Turkish.
        with patch.dict('os.environ', {'PYTHONIOENCODING': 'cp1254'}):
            transport.WorkerSession(events.append).run({'action': 'test-sources', 'source_mode': 'corporate'})
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        checks = next(event['checks'] for event in events if event['type'] == 'checks')
        self.assertIn('seçin', checks[0]['detail'])


if __name__ == '__main__':
    unittest.main()
