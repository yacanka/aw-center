"""Independent desktop task lifecycles, without needing a Tk display."""
from pathlib import Path
import os
import threading
import unittest
from unittest.mock import Mock, patch

from scripts.manager.controller import ManagerController


class FakeSession:
    def __init__(self, emit):
        self.emit = emit
        self.started = threading.Event()
        self.release = threading.Event()
        self.stopped = False
        self.sent = []

    def run(self, request):
        self.request = dict(request)
        self.started.set()
        self.release.wait(5)

    def stop(self):
        self.stopped = True

    def send(self, value):
        self.sent.append(value)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.root, self.view = Mock(), Mock()
        self.sessions = []
        def factory(emit):
            session = FakeSession(emit)
            self.sessions.append(session)
            return session
        self.browser = Mock()
        self.controller = ManagerController(self.root, Mock(return_value=self.view), Path.cwd(),
                                            session_factory=factory, browser_opener=self.browser)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for session in self.sessions:
            session.release.set()

    def start(self, action, profile='dev', **values):
        task_id = self.controller.action(action, {'profile': profile, 'source_root': '/source', **values})
        if task_id is not None:
            self.assertTrue(self.sessions[-1].started.wait(1))
        return task_id

    def event(self, task_id, **event):
        self.controller.events.put({**event, 'task_id': task_id})
        self.controller.poll()

    def test_running_app_does_not_block_source_probe_or_doctor(self):
        run_id = self.start('start')
        source_id = self.start('test-sources')
        doctor_id = self.start('doctor')
        self.assertEqual(len({run_id, source_id, doctor_id}), 3)
        self.assertEqual(len(self.sessions), 3)
        self.assertFalse(any(session.stopped for session in self.sessions))

    def test_conflict_is_visible_without_disturbing_running_task(self):
        first = self.start('start')
        self.assertIsNone(self.start('provision'))
        self.assertEqual(len(self.sessions), 1)
        event = self.view.handle_event.call_args.args[0]
        self.assertEqual(event['code'], 'task_conflict')
        self.assertIn(first, self.controller.tasks)
        self.assertFalse(self.sessions[0].stopped)

    def test_claims_and_worker_receive_the_same_absolute_output(self):
        task_id = self.start('bundle', output='manager-output')
        output = self.controller.tasks[task_id].values['output']
        self.assertTrue(Path(output).is_absolute())
        self.assertEqual(self.sessions[0].request['output'], output)
        self.assertIsNone(self.start('bundle', output=output))

    def test_automatic_bundle_output_is_unique_and_claimed_before_worker_starts(self):
        local = Path.cwd() / 'operator-local'
        with patch.dict(os.environ, {'LOCALAPPDATA': str(local)}), \
             patch.object(Path, 'exists', side_effect=AssertionError('No disk checks on Tk')):
            first = self.start('bundle')
            second = self.start('bundle')
        first_output = self.controller.tasks[first].values['output']
        second_output = self.controller.tasks[second].values['output']
        self.assertNotEqual(first_output, second_output)
        self.assertEqual(Path(first_output).parent, local / 'AWCenter' / 'exports')
        self.assertEqual(self.sessions[0].request['output'], first_output)
        self.assertTrue(any(claim.path and claim.write and claim.resource == first_output
                            for claim in self.controller.tasks[first].claims))

    def test_ready_provision_releases_setup_claim_for_bundle(self):
        task_id = self.start('provision')
        self.assertIsNone(self.start('bundle', output='/out'))
        self.event(task_id, type='ready', url='http://127.0.0.1:5173/app/')
        self.assertIsNotNone(self.start('bundle', output='/out'))

    def test_error_and_cleanup_affect_only_their_task(self):
        run_id = self.start('start')
        probe_id = self.start('test-sources')
        self.event(probe_id, type='error', code='source_failed', message='safe error')
        self.event(probe_id, type='done', ok=False)
        self.event(probe_id, type='_closed')
        self.assertEqual(self.controller.tasks[probe_id].status, 'failed')
        self.assertTrue(self.controller.tasks[run_id].active)
        self.assertFalse(self.sessions[0].stopped)
        self.root.destroy.assert_not_called()

    def test_stop_targets_selected_operation(self):
        run_id = self.start('start')
        source_id = self.start('test-sources')
        self.view.selected_task_id.return_value = source_id
        self.controller.stop()
        self.assertFalse(self.sessions[0].stopped)
        self.assertTrue(self.sessions[1].stopped)
        self.assertTrue(self.controller.tasks[run_id].active)

    def test_done_keeps_conflict_until_process_cleanup(self):
        task_id = self.start('start')
        self.event(task_id, type='done', ok=True)
        self.assertEqual(self.controller.tasks[task_id].status, 'finishing')
        self.assertIsNone(self.start('start'))
        self.event(task_id, type='_closed')
        self.assertIsNotNone(self.start('start'))

    def test_admin_response_is_callback_based_and_bound_to_own_task(self):
        setup = self.start('provision')
        probe = self.start('test-sources')
        self.event(setup, type='input', kind='admin')
        task_id, callback = self.view.request_admin.call_args.args
        self.assertEqual(task_id, setup)
        self.event(probe, type='status', message='other task still progressing')
        self.assertEqual(self.view.handle_event.call_args.args[0]['task_id'], probe)
        callback({'username': 'U12345', 'password': 'not-a-real-password'})
        self.assertEqual(len(self.sessions[0].sent), 1)
        self.assertEqual(self.sessions[1].sent, [])

    def test_close_cancels_all_and_waits_for_all_cleanup(self):
        first, second = self.start('start'), self.start('test-sources')
        self.view.confirm_stop.return_value = True
        self.controller.close()
        self.assertTrue(all(session.stopped for session in self.sessions))
        self.root.destroy.assert_not_called()
        self.event(first, type='_closed')
        self.root.destroy.assert_not_called()
        self.event(second, type='_closed')
        self.root.destroy.assert_called_once()

    def test_blocked_browser_does_not_block_other_events(self):
        gate, started = threading.Event(), threading.Event()
        def blocked(_url):
            started.set()
            gate.wait(3)
        self.controller.browser_opener = blocked
        task_id = self.start('start')
        try:
            self.event(task_id, type='ready', url='http://127.0.0.1:5173/app/')
            self.assertTrue(started.wait(1))
            probe_id = self.start('test-sources')
            self.event(probe_id, type='status', message='not blocked')
            self.assertEqual(self.view.handle_event.call_args.args[0]['message'], 'not blocked')
        finally:
            gate.set()

    def test_broken_view_does_not_stop_events_for_other_tasks(self):
        first, second = self.start('start'), self.start('test-sources')
        def render(event):
            if event.get('message') == 'first':
                raise RuntimeError('render failed')
        self.view.handle_event.side_effect = render
        self.controller.events.put({'type': 'status', 'task_id': first, 'message': 'first'})
        self.controller.events.put({'type': 'status', 'task_id': second, 'message': 'second'})
        self.controller.poll()
        self.assertEqual(self.view.handle_event.call_args.args[0]['message'], 'second')
        self.root.after.assert_called()

    def test_noisy_task_cannot_starve_an_independent_completion(self):
        first, second = self.start('start'), self.start('test-sources')
        for index in range(150):
            self.sessions[0].emit({'type': 'status', 'message': f'noisy-{index}'})
        self.sessions[1].emit({'type': 'done', 'ok': True})
        self.sessions[1].emit({'type': '_closed'})
        self.controller.poll()
        self.assertEqual(self.controller.tasks[second].status, 'done')
        self.assertTrue(self.controller.tasks[first].active)

    def test_failed_prompt_cleanup_cannot_strand_window_close(self):
        task_id = self.start('start')
        self.controller.closing = True
        self.view.dismiss_admin.side_effect = RuntimeError('view unavailable')
        self.event(task_id, type='_closed')
        self.root.destroy.assert_called_once()

    def test_close_cancels_every_task_even_if_one_prompt_cannot_close(self):
        self.start('start')
        self.start('test-sources')
        self.view.confirm_stop.return_value = True
        self.view.dismiss_admin.side_effect = RuntimeError('view unavailable')
        self.controller.close()
        self.assertTrue(all(session.stopped for session in self.sessions))


if __name__ == '__main__':
    unittest.main()
