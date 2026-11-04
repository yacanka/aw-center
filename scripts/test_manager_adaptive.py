"""Profile actions follow lifecycle truth, independently of selected reports."""
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile

from scripts.manager.view_model import ManagerState, ManagerTaskStates
from scripts import test_manager_controller as fixtures


class InspectionTests(unittest.TestCase):
    def test_canonical_prod_provision_acquires_write_claim_before_nested_lifecycle(self):
        from scripts.manager import operations
        from scripts.launcher_test_support import create_project
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve() / 'home'
            source = home / 'releases' / ('a' * 64) / 'source'
            source.mkdir(parents=True)
            from scripts.launcher.installation_permissions import secure_path
            secure_path(home)
            project = create_project(source)
            args = operations.arguments({'action': 'provision', 'profile': 'prod'})
            args.source_root, args.progress = str(source), lambda _: None
            with patch('scripts.launcher.installation_profiles.installation_home', return_value=home), \
                 patch.object(operations, '_project_for', return_value=project), \
                 patch.object(operations, '_run_lifecycle') as provision:
                operations._dispatch('provision', args, lambda _: None)
            provision.assert_called_once()

    def test_new_profile_inspection_does_not_create_state(self):
        from scripts.manager import inspection, operations
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve() / 'not-created'
            events = []
            with patch.object(inspection, 'installation_home', return_value=home), \
                 patch.object(inspection, 'require_windows'), \
                 patch('scripts.launcher.runtime_selection.tool_choices', return_value={}):
                inspection.inspect_profile(operations.arguments({'action': 'inspect'}), events.append)
            self.assertEqual(events[-1]['status'], 'not_installed')
            self.assertIn('Python 3.11', events[-1]['tools'])
            self.assertFalse(home.exists())

    def test_existing_canonical_profile_is_detected_as_prepared(self):
        from scripts.manager import inspection, operations
        from scripts.launcher.installation_profiles import provision_profile
        from scripts.launcher_test_support import create_project
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / 'source').mkdir()
            project = create_project(root / 'source')
            home = root / 'private'
            provision_profile(project, 'dev', home)
            events = []
            with patch.object(inspection, 'installation_home', return_value=home), \
                 patch.object(inspection, 'require_windows'), \
                 patch.object(operations, '_project_for', return_value=project), \
                 patch.object(inspection, 'inspect_toolchain', return_value=[{'status': 'ready'}]), \
                 patch.object(inspection, '_core_checks', return_value=[]):
                inspection.inspect_profile(operations.arguments({'action': 'inspect'}), events.append)
            self.assertEqual(events[-1]['status'], 'stopped')


class AdaptiveStateTests(unittest.TestCase):
    def test_completed_lifecycle_drops_live_url(self):
        state = ManagerState()
        state.handle_event({'type': 'ready', 'url': 'http://127.0.0.1:5173/app/'})
        state.handle_event({'type': 'done', 'ok': True, 'cancelled': True})
        self.assertEqual(state.ready_url, '')

    def test_checks_cannot_hide_blockers_behind_generic_success(self):
        state = ManagerState()
        state.handle_event({'type': 'checks', 'checks': [{'name': 'database', 'status': 'blocked', 'detail': 'missing'}]})
        state.handle_event({'type': 'done', 'ok': True})
        self.assertIn('engellendi', state.status.lower())

    def test_profile_action_survives_selecting_source_test(self):
        states = ManagerTaskStates()
        states.update_tasks([
            {'id': 'server', 'action': 'start', 'profile': 'dev', 'status': 'ready'},
            {'id': 'probe', 'action': 'test-sources', 'profile': 'dev', 'status': 'running'}], 'probe')
        states.handle_event({'task_id': 'server', 'type': 'ready', 'url': 'http://127.0.0.1:5173/app/'})
        self.assertTrue(hasattr(states, 'profile_presentation'), 'Independent profile presentation is missing')
        presentation = states.profile_presentation('dev')
        self.assertEqual(presentation['action'], 'open')
        self.assertEqual(presentation['task_id'], 'server')
        self.assertEqual(states.selected_id, 'probe')

    def test_profile_inspection_selects_install_or_start_and_does_not_select_a_report(self):
        states = ManagerTaskStates()
        states.handle_event({'type': 'profile', 'profile': 'dev', 'status': 'not_installed', 'checks': []})
        self.assertTrue(hasattr(states, 'profile_presentation'), 'Independent profile presentation is missing')
        self.assertEqual(states.profile_presentation('dev')['action'], 'provision')
        states.handle_event({'type': 'profile', 'profile': 'dev', 'status': 'stopped', 'checks': []})
        self.assertEqual(states.profile_presentation('dev')['action'], 'start')
        self.assertIsNone(states.selected_id)


class AdaptiveControllerTests(unittest.TestCase):
    setUp = fixtures.ControllerTests.setUp
    cleanup = fixtures.ControllerTests.cleanup
    start = fixtures.ControllerTests.start
    event = fixtures.ControllerTests.event

    def test_window_close_minimizes_active_work_without_cancelling(self):
        self.start('start')
        self.assertTrue(hasattr(self.controller, 'window_close'), 'Minimize-on-close is missing')
        self.controller.window_close()
        self.root.iconify.assert_called_once()
        self.assertFalse(any(session.stopped for session in self.sessions))
        self.view.confirm_stop.assert_not_called()

    def test_repeated_ready_event_opens_browser_once(self):
        task = self.start('start')
        self.controller.open_browser = Mock()
        self.event(task, type='ready', url='http://127.0.0.1:5173/app/')
        self.event(task, type='ready', url='http://127.0.0.1:5173/app/')
        self.controller.open_browser.assert_called_once()

    def test_old_inspection_cannot_replace_new_source_inspection(self):
        self.view.form_values.return_value = {'profile': 'dev', 'source_root': '/old'}
        self.controller.inspect_selected()
        old = self.controller.inspection_ids['dev']
        self.view.form_values.return_value = {'profile': 'dev', 'source_root': '/new'}
        self.controller.inspect_selected()
        new = self.controller.inspection_ids['dev']
        self.view.handle_event.reset_mock()
        self.event(old, type='profile', profile='dev', status='stopped')
        self.view.handle_event.assert_not_called()
        self.event(new, type='profile', profile='dev', status='not_installed')
        self.assertEqual(self.view.handle_event.call_args.args[0]['status'], 'not_installed')
