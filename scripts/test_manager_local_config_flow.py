"""Local configuration is reflected in real launch decisions and access URLs."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.launcher import installation, installation_profiles as profiles
from scripts.launcher import installation_readiness as readiness
from scripts.launcher_test_support import create_project
from scripts.manager import operations


class LocalAccessTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'name': 'dev', 'host': '0.0.0.0', 'backend_port': 18000,
                        'frontend_port': 15173}

    def test_health_checks_wildcard_binding_through_loopback(self):
        with patch.object(readiness, 'probe_http', return_value=True) as http:
            self.assertTrue(readiness.healthy(self.profile, lambda: True))
        self.assertEqual([call.args[0] for call in http.call_args_list],
                         ['http://127.0.0.1:18000/health/live/', 'http://127.0.0.1:15173/app/'])
        self.assertEqual(self.profile['host'], '0.0.0.0')

    def test_first_readiness_checks_wildcard_binding_through_loopback(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory)
            for role in ('job', 'notification', 'cleanup'):
                (heartbeat / role).touch()
            child = Mock()
            child.poll.return_value = None
            with patch.object(readiness, 'probe_http', return_value=True) as http:
                readiness.wait_until_ready([child], self.profile, heartbeat, worker_check=lambda: True)
        self.assertEqual([call.args[0] for call in http.call_args_list],
                         ['http://127.0.0.1:18000/health/live/', 'http://127.0.0.1:15173/app/'])

    def test_browser_ready_event_uses_loopback_without_changing_bind_host(self):
        events = []
        args = operations.arguments({'action': 'start'})
        args.progress = lambda _message: None
        def start(project, name, *, on_ready, on_health):
            on_ready(self.profile)
        with patch.object(installation, 'start_profile', side_effect=start):
            operations._run_lifecycle(None, 'start', args, events.append, ensured=True)
        self.assertEqual(events, [{'type': 'ready', 'url': 'http://127.0.0.1:15173/app/'}])
        self.assertEqual(self.profile['host'], '0.0.0.0')


class LocalConfigurationFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        source = self.root / 'source'
        source.mkdir()
        self.project = create_project(source)
        self.home = self.root / 'private'
        self.source_env = self.root / 'application.env'
        self.environment = patch.dict('os.environ', {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        location = patch.object(profiles, 'installation_home', return_value=self.home)
        location.start()
        self.addCleanup(location.stop)
        self.launches = []

    def run_manager(self, **overrides):
        events = []
        def provision(project, args):
            profiles.provision_profile(project, 'dev', self.home)
            return []
        def start(project, name, *, on_ready, on_health, validation_policy='managed'):
            profile = profiles.load_profile(project, name, self.home)
            self.launches.append((profile, profiles.read_profile_environment(profile)))
            on_ready(profile)
        ready = [{'name': 'core', 'status': 'ready'}]
        request = {'action': 'ensure', 'source_root': str(self.project.root),
                   'env_file': str(self.source_env), **overrides}
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch.object(installation, 'provision', side_effect=provision), \
             patch.object(installation, 'start_profile', side_effect=start), \
             patch.object(installation, '_core_checks', return_value=ready), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=ready):
            operations.execute(request, events.append, lambda: None, threading.Event())
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        return self.launches[-1]

    def test_main_action_applies_manager_override_then_falls_back_when_cleared(self):
        content = 'PORT=18001\nDEV_FRONTEND_PORT=15173\nLOG_LEVEL=DEBUG\n'
        self.source_env.write_text(content)
        first, values = self.run_manager(backend_port='18002')
        self.assertEqual(first['backend_port'], 18002)
        self.assertEqual(values['PORT'], '18002')
        self.assertEqual(values['LOG_LEVEL'], 'DEBUG')
        second, values = self.run_manager(backend_port='')
        self.assertEqual(second['backend_port'], 18001)
        self.assertEqual(values['PORT'], '18001')
        self.assertEqual(self.source_env.read_text(), content)

    def test_main_action_rereads_changed_env_and_removes_deleted_setting(self):
        self.source_env.write_text('PORT=18003\nDEV_FRONTEND_PORT=15174\nEMAIL_HOST=first.example.invalid\n')
        first, before = self.run_manager()
        self.source_env.write_text('PORT=18004\nDEV_FRONTEND_PORT=15174\n')
        second, after = self.run_manager(validation_policy='developer')
        self.assertEqual(first['backend_port'], 18003)
        self.assertEqual(second['backend_port'], 18004)
        self.assertEqual(before['EMAIL_HOST'], 'first.example.invalid')
        self.assertNotIn('EMAIL_HOST', after)
        self.assertEqual(before['SECRET_KEY'], after['SECRET_KEY'])

    def test_readonly_source_check_reuses_explicit_override_provenance(self):
        from scripts.launcher.installation_local_config import apply_local_configuration
        self.source_env.write_text('PORT=18005\nDEV_FRONTEND_PORT=15175\n')
        args = operations.arguments({'action': 'ensure', 'backend_port': '18006',
                                     'env_file': str(self.source_env)})
        profile = apply_local_configuration(self.project, args)
        original = Path(profile['env_file']).read_bytes()
        readonly = operations.arguments({'action': 'doctor', 'env_file': str(self.source_env)})

        operations._check_environment_source(self.project, profile, readonly)

        self.assertIsNone(readonly.backend_port)
        self.assertEqual(Path(profile['env_file']).read_bytes(), original)

    def test_readonly_source_change_requests_main_action_without_writing(self):
        from scripts.launcher.installation_local_config import apply_local_configuration
        from scripts.launcher.installation_profiles import EnvironmentImportError
        self.source_env.write_text('PORT=18007\nDEV_FRONTEND_PORT=15176\n')
        args = operations.arguments({'action': 'ensure', 'env_file': str(self.source_env)})
        profile = apply_local_configuration(self.project, args)
        original = Path(profile['env_file']).read_bytes()
        self.source_env.write_text('PORT=18008\nDEV_FRONTEND_PORT=15176\n')
        readonly = operations.arguments({'action': 'start', 'env_file': str(self.source_env)})

        with self.assertRaises(EnvironmentImportError) as caught:
            operations._check_environment_source(self.project, profile, readonly)

        self.assertEqual(caught.exception.code, 'env_import_required')
        self.assertEqual(Path(profile['env_file']).read_bytes(), original)
