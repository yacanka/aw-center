"""One-click decisions use real profile state and never swallow startup errors."""
import os
import errno
import tempfile
import unittest
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.launcher_test_support import create_project
from scripts.launcher import installation_profiles as profiles
from scripts.manager import operations
from scripts.manager.view_model import ManagerTaskStates, normalize_values


class EnsureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'source').mkdir()
        self.project = create_project(self.root / 'source')
        self.home = self.root / 'home'
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.location = patch('scripts.launcher.installation_profiles.installation_home', return_value=self.home)
        self.location.start()
        self.addCleanup(self.location.stop)

    def args(self, **values):
        args = operations.arguments({'action': 'ensure', **values})
        args.source_root = str(self.project.root)
        args.progress = lambda message: None
        return args

    def test_ensure_admits_advanced_inputs(self):
        args = self.args(frontend_port='15173', env_file='/selected.env', migration_policy='confirm')
        self.assertEqual(args.frontend_port, 15173)
        self.assertEqual(args.env_file, Path('/selected.env'))
        self.assertEqual(args.migration_policy, 'confirm')

    def test_main_action_prepares_pending_environment_without_advanced_settings(self):
        state = ManagerTaskStates()
        state.handle_event({'type': 'profile', 'profile': 'dev', 'status': 'incomplete'})
        self.assertEqual(state.profile_presentation('dev')['action'], 'ensure')
        values = normalize_values('ensure', {'backend_port': 'auto', 'frontend_port': 'auto'})
        self.assertEqual(values['migration_policy'], 'automatic')

    def test_fresh_profile_selects_provision_without_creating_storage(self):
        from scripts.manager.ensure import needs_preparation
        self.assertTrue(needs_preparation(self.project, self.args()))
        self.assertFalse(self.home.exists())

    def test_prepared_profile_selects_start_but_changed_input_selects_preparation(self):
        from scripts.manager.ensure import needs_preparation
        profiles.provision_profile(self.project, 'dev', self.home)
        ready = [{'name': 'database', 'status': 'ready'}]
        with patch('scripts.launcher.installation._core_checks', return_value=ready), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=ready):
            self.assertFalse(needs_preparation(self.project, self.args()))
            self.assertTrue(needs_preparation(self.project, self.args(frontend_port='15173')))

    def test_automatic_source_uses_recorded_profile_without_rebinding(self):
        from scripts.manager.ensure import resolve_source
        profiles.provision_profile(self.project, 'dev', self.home)
        args = self.args(source_selection='automatic')
        args.source_root = str(self.root / 'new-package/source')
        resolve_source(args)
        self.assertEqual(Path(args.source_root), self.project.root)
        explicit = self.args(source_selection='explicit')
        explicit.source_root = str(self.root / 'operator-source')
        resolve_source(explicit)
        self.assertEqual(Path(explicit.source_root), self.root / 'operator-source')

    def test_one_click_creates_profile_then_restart_preserves_configuration(self):
        events, preparations = [], []
        def provision(project, args):
            preparations.append(args.profile)
            profiles.provision_profile(project, args.profile, self.home,
                backend_port=args.backend_port, frontend_port=args.frontend_port,
                port_modes=args.port_modes)
            return []
        def start(project, name, on_ready, on_health):
            on_ready(profiles.load_profile(project, name, self.home))
        ready = [{'name': 'core', 'status': 'ready'}]
        request = {'action': 'ensure', 'source_root': str(self.project.root)}
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch('scripts.launcher.installation.provision', side_effect=provision), \
             patch('scripts.launcher.installation.start_profile', side_effect=start), \
             patch('scripts.launcher.installation._core_checks', return_value=ready), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=ready):
            operations.execute(request, events.append, lambda: None, threading.Event())
            self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
            before = (self.home / 'config/dev.env').read_bytes()
            operations.execute(request, events.append, lambda: None, threading.Event())
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(preparations, ['dev'])
        self.assertEqual(before, (self.home / 'config/dev.env').read_bytes())
        self.assertEqual(len([event for event in events if event['type'] == 'ready']), 2)

    def test_ready_profile_with_unknown_migration_history_cannot_start(self):
        from scripts.manager.ensure import needs_preparation
        from scripts.launcher.model import LauncherError
        profiles.provision_profile(self.project, 'dev', self.home)
        self.project.python.parent.mkdir(parents=True, exist_ok=True)
        self.project.python.touch()
        with patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
             patch('scripts.launcher.installation.backend_inspection',
                   return_value={'schema': 'ready', 'auto_migrate_safe': False}):
            with self.assertRaises(LauncherError):
                needs_preparation(self.project, self.args())

    def test_snapshot_integration_observes_operation_cancellation(self):
        from scripts.launcher.installation import _initialize_schema
        from scripts.launcher.process import OperationCancelled, operation_control
        profile = profiles.provision_profile(self.project, 'dev', self.home)
        args = self.args()
        args.manager_ensure = True
        stop = threading.Event()
        def snapshot(*_args, **kwargs):
            stop.set()
            kwargs['cancelled']()
            self.fail('Stop request was ignored')
        with patch('scripts.launcher.installation_backup.run_backed_up_migrations', side_effect=snapshot), \
             operation_control(stop):
            with self.assertRaises(OperationCancelled):
                _initialize_schema(self.project, profile, args, {})

    def test_startup_repairs_directory_inheritance_before_reading_automatic_source(self):
        from scripts.launcher import installation_permissions as permissions
        profile = profiles.provision_profile(self.project, 'dev', self.home)
        original = Path(profile['env_file']).read_bytes()
        inherited = {self.home, self.home / 'config'}
        def native(path, *, apply, repair_inheritance=False, file_descriptor=None):
            if path not in inherited:
                return False
            if apply or repair_inheritance:
                inherited.remove(path)
                return True
            raise permissions.PermissionCheckError('acl_inheritance')
        ready = [{'name': 'core', 'status': 'ready'}]
        def start(project, name, on_ready, on_health):
            on_ready(profiles.load_profile(project, name, self.home))
        events = []
        with patch.object(permissions, 'os', SimpleNamespace(name='nt', path=os.path)), \
             patch.object(permissions, '_windows_permissions', side_effect=native), \
             patch('scripts.launcher.installation_state.require_local_ntfs'), \
             patch.object(operations, '_project_for', return_value=self.project), \
             patch('scripts.launcher.installation._core_checks', return_value=ready), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=ready), \
             patch('scripts.launcher.installation.start_profile', side_effect=start):
            operations.execute({'action': 'ensure', 'source_selection': 'automatic',
                                'source_root': str(self.project.root)},
                               events.append, lambda: None, threading.Event())
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(inherited, set())
        self.assertEqual(Path(profile['env_file']).read_bytes(), original)
        self.assertTrue(any(event['type'] == 'ready' for event in events))

    def test_storage_write_failure_is_detected_before_starting_prepared_application(self):
        from scripts.launcher import installation_state as state
        profiles.provision_profile(self.project, 'dev', self.home)
        error = PermissionError(errno.EACCES, 'private-path-withheld')
        error.winerror = 5
        events = []
        ready = [{'name': 'core', 'status': 'ready'}]
        with patch.object(state.os, 'replace', side_effect=error), \
             patch.object(operations, '_project_for', return_value=self.project), \
             patch('scripts.launcher.installation._core_checks', return_value=ready), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=ready), \
             patch('scripts.launcher.installation.start_profile', side_effect=lambda *_, **__: None):
            operations.execute({'action': 'ensure', 'source_root': str(self.project.root)},
                               events.append, lambda: None, threading.Event())
        self.assertEqual(events[-1], {'type': 'done', 'ok': False}, events)
        failure = next(event for event in events if event['type'] == 'error')
        self.assertEqual(failure['code'], 'system_access_denied')
        self.assertIn('yazma', failure['message'])
        self.assertNotIn('private-path-withheld', failure['message'])
        self.assertFalse(any(event['type'] == 'ready' for event in events))
