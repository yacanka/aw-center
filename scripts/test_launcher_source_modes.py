"""Explicit source modes never silently widen acquisition to public services."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from io import StringIO
from contextlib import nullcontext
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts.launcher import installation_sources as sources
from scripts.launcher.model import LauncherError
from scripts.launcher.parser import build_parser
from scripts.test_launcher import create_project


class SourceModeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'source').mkdir()
        self.project = create_project(self.root / 'source')
        (self.project.frontend / 'package-lock.json').write_text('{}')
        self.artifact = sources.Artifact('example', '1', 'example.zip', 'https://public.example/example.zip',
                                         hashlib.sha256(b'reviewed').hexdigest(), 'zip', 'example.exe')

    def test_default_cli_preserves_online_and_explicit_modes_parse(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(['provision']).source_mode, 'online')
        for mode in ('online', 'corporate', 'offline'):
            self.assertEqual(parser.parse_args(['provision', '--source-mode', mode]).source_mode, mode)

    def test_corporate_artifact_does_not_request_public_source(self):
        urls = []
        def retrieve(url, destination, context):
            urls.append(url)
            destination.write_bytes(b'reviewed')
            return True
        with mock.patch.object(sources, '_retrieve', side_effect=retrieve):
            sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings(
                repository='https://selected.example/tools', mode='corporate'))
        self.assertEqual(urls, ['https://selected.example/tools/example.zip'])

    def test_offline_artifact_never_attempts_network(self):
        offline = self.root / 'offline'
        offline.mkdir()
        (offline / self.artifact.filename).write_bytes(b'reviewed')
        with mock.patch.object(sources, '_retrieve', side_effect=AssertionError('network attempted')):
            result = sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings(
                repository='https://selected.example/tools', offline_dir=offline, mode='offline',
                ca_file=self.root / 'unavailable-ca.pem'))
        self.assertEqual(result.read_bytes(), b'reviewed')

    def test_unknown_mode_fails_before_acquisition(self):
        with self.assertRaises(LauncherError):
            sources.SourceSettings(mode='unexpected')

    def test_package_acquisition_obeys_corporate_and_offline_modes(self):
        from scripts.launcher import installation_dependencies as dependencies
        offline = self.root / 'offline'
        (offline / 'npm-cache').mkdir(parents=True)
        (offline / 'wheels').mkdir()
        for mode in ('corporate', 'offline'):
            with self.subTest(mode=mode):
                stage = self.root / (mode + '-stage')
                stage.mkdir()
                commands = []
                def capture(command, *_):
                    commands.append([str(part) for part in command])
                    return subprocess.CompletedProcess(command, 0, '', '')
                settings = sources.SourceSettings(mode=mode, offline_dir=offline,
                    python_index_url='https://selected.example/simple', npm_registry_url='https://selected.example/npm')
                with mock.patch.object(dependencies, 'capture', side_effect=capture), \
                     mock.patch.object(dependencies, '_npm_command', return_value=['npm']), \
                     mock.patch.object(dependencies, '_offline_dependencies', return_value=offline):
                    dependencies._python_packages(self.project, settings, {}, stage)
                    dependencies._frontend_packages(self.project, settings, {}, stage)
                flattened = ' '.join(' '.join(command) for command in commands)
                self.assertNotIn('pypi.org', flattened)
                self.assertNotIn('registry.npmjs.org', flattened)
                self.assertFalse(any('--index-url' in command or '--registry' in command for command in commands))
                self.assertTrue(all('--offline' in command for command in commands if 'ci' in command))

    def test_bundle_acquisition_uses_same_source_policy(self):
        from scripts.launcher import installation_bundle as bundle
        offline = self.root / 'offline'
        (offline / 'wheels').mkdir(parents=True)
        (offline / 'wheels' / 'fixture.whl').write_bytes(b'wheel')
        (offline / 'npm-cache' / '_cacache').mkdir(parents=True)
        (offline / 'npm-cache' / '_cacache' / 'fixture').write_bytes(b'package')
        for mode in ('corporate', 'offline'):
            commands = []
            def capture(command, *_):
                commands.append([str(part) for part in command])
                if 'wheel' in command:
                    (Path(command[command.index('--wheel-dir') + 1]) / 'fixture.whl').write_bytes(b'wheel')
                if '--registry' in command:
                    (Path(command[command.index('--cache') + 1]) / '_cacache').mkdir(parents=True)
                return subprocess.CompletedProcess(command, 0, '', '')
            settings = sources.SourceSettings(mode=mode, offline_dir=offline,
                python_index_url='https://selected.example/simple', npm_registry_url='https://selected.example/npm')
            with mock.patch.object(bundle, '_capture', side_effect=capture), \
                 mock.patch.object(bundle, '_npm_argv', return_value=['npm']), \
                 mock.patch.object(bundle, '_offline_source', return_value=offline):
                bundle._acquire_wheels(self.project, self.root / (mode + '-wheels'), settings, {})
                bundle._acquire_npm(self.project, self.root / (mode + '-npm'), settings, {})
            flattened = ' '.join(' '.join(command) for command in commands)
            self.assertNotIn('pypi.org', flattened)
            self.assertNotIn('registry.npmjs.org', flattened)
            if mode == 'offline':
                self.assertFalse(any('--index-url' in command or '--registry' in command for command in commands))

    def test_mode_preferences_round_trip_and_legacy_defaults_online(self):
        from scripts.launcher.installation import source_settings
        from scripts.launcher.installation_state import load_sources, save_sources
        home = self.root / 'home'
        save_sources(home, sources.SourceSettings(mode='offline', offline_dir=self.root))
        self.assertEqual(load_sources(home)['mode'], 'offline')
        with mock.patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)}), \
             mock.patch('scripts.launcher.installation.installation_home', return_value=home):
            self.assertEqual(source_settings(SimpleNamespace()).mode, 'offline')
            self.assertEqual(source_settings(SimpleNamespace(source_mode='corporate')).mode, 'corporate')
        with mock.patch('scripts.launcher.installation.load_sources', return_value={}), \
             mock.patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)}):
            self.assertEqual(source_settings(SimpleNamespace()).mode, 'online')

    def test_explicit_gui_sources_do_not_reuse_saved_or_inherited_choices(self):
        from scripts.launcher.installation import source_settings
        saved = {'repository': 'https://saved.example/tools', 'offline_dir': str(self.root / 'saved'),
                 'python_index_url': 'https://saved.example/simple',
                 'npm_registry_url': 'https://saved.example/npm', 'mode': 'corporate',
                 'ca_file': str(self.root / 'saved.pem')}
        inherited = {'LOCALAPPDATA': str(self.root),
                     'AWCENTER_PACKAGE_REPOSITORY': 'https://inherited.example/tools',
                     'AWCENTER_OFFLINE_DIR': str(self.root / 'inherited')}
        with mock.patch.dict(os.environ, inherited), \
             mock.patch('scripts.launcher.installation.load_sources', return_value=saved):
            settings = source_settings(SimpleNamespace(use_saved_sources=False))
        self.assertEqual(settings, sources.SourceSettings())

    def test_gui_explicit_sources_remain_selected_when_preferences_are_disabled(self):
        from scripts.launcher.installation import source_settings
        args = SimpleNamespace(use_saved_sources=False, source_mode='corporate',
            repository='https://selected.example/tools', offline_dir=self.root / 'selected',
            python_index_url='https://selected.example/simple', npm_registry_url='https://selected.example/npm',
            ca_file=self.root / 'selected.pem')
        self.assertEqual(source_settings(args), sources.SourceSettings(mode='corporate',
            repository=args.repository, offline_dir=args.offline_dir,
            python_index_url=args.python_index_url, npm_registry_url=args.npm_registry_url,
            ca_file=args.ca_file))


class EngineHookTests(unittest.TestCase):
    def test_provision_emits_real_phase_labels_before_each_stage(self):
        from scripts.launcher import installation
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            labels = []
            profile = {'name': 'dev', 'env_file': str(root / 'private.env')}
            args = SimpleNamespace(profile='dev', progress=labels.append)
            with mock.patch.object(installation, 'require_windows'), \
                 mock.patch.object(installation, 'installation_home', return_value=root), \
                 mock.patch.object(installation, 'source_settings', return_value=sources.SourceSettings()), \
                 mock.patch.object(installation, 'installation_lock', return_value=nullcontext()), \
                 mock.patch.object(installation, 'save_report'), \
                 mock.patch.object(installation, 'save_sources'), \
                 mock.patch.object(installation, 'provision_profile', return_value=profile), \
                 mock.patch.object(installation, 'profile_environment', return_value={}), \
                 mock.patch.object(installation, 'ensure_toolchain', return_value={'AWCENTER_MANAGED_PYTHON': '/python'}), \
                 mock.patch('scripts.launcher.runtime_selection.tool_choices', return_value={}), \
                 mock.patch('scripts.launcher.installation_profiles.update_python_runtime', return_value=profile), \
                 mock.patch('scripts.launcher.installation_profiles.update_node_runtime', return_value=profile), \
                 mock.patch.object(installation, 'install_dependencies'), \
                 mock.patch.object(installation, '_initialize_schema'), \
                 mock.patch.object(installation, '_initial_admin'), \
                 mock.patch.object(installation, '_select_assets', return_value=profile), \
                 mock.patch.object(installation, '_core_checks', return_value=[]), \
                 mock.patch('scripts.launcher.installation_features.install_features', return_value=[]), \
                 mock.patch('builtins.print'):
                self.assertEqual(installation.provision(project, args), [])
            self.assertEqual(labels, ['ön kontrol', 'runtime hazırlığı', 'kilitli bağımlılıklar', 'özel profil',
                                     'veritabanı şeması', 'ilk yönetici', 'ek araçlar ve varlıklar'])

    def test_running_callback_occurs_only_after_readiness_succeeds(self):
        from scripts.launcher import installation
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            profile = {'name': 'dev', 'host': '127.0.0.1', 'backend_port': 8000,
                       'frontend_port': 5173, 'env_file': str(root / 'private.env')}
            events = []
            def run(*_, **options):
                options['ready']([])
            with mock.patch.object(installation, 'require_windows'), \
                 mock.patch.object(installation, 'load_profile', return_value=profile), \
                 mock.patch.object(installation, 'inspect_toolchain', return_value=[]), \
                 mock.patch.object(installation, 'profile_environment', return_value={}), \
                 mock.patch('scripts.launcher.toolchain.toolchain_environment', return_value={}), \
                 mock.patch('scripts.launcher.installation_features.feature_environment', return_value={}), \
                 mock.patch.object(installation, 'runtime_session', return_value=nullcontext(root)), \
                 mock.patch.object(installation, '_django'), \
                 mock.patch.object(installation, 'wait_until_ready', side_effect=lambda *_, **__: events.append('checked')), \
                 mock.patch.object(installation.runtime, 'dev', side_effect=run):
                installation.start_profile(project, 'dev', on_ready=lambda ready: events.append(ready['name']))
            self.assertEqual(events, ['checked', 'dev'])


class InitialAdminTransportTests(unittest.TestCase):
    def test_gui_credentials_use_explicit_interpreter_and_private_stdin_only(self):
        from scripts.launcher.installation import _initial_admin
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            credential = {'username': 'U12345', 'password': 'transport-fixture-only'}
            provider = mock.Mock(return_value=credential)
            args = SimpleNamespace(no_admin=False, admin_provider=provider)
            with mock.patch('scripts.launcher.installation.backend_inspection', return_value={'admin_exists': False}), \
                 mock.patch('scripts.launcher.installation.profile_environment', return_value={}), \
                 mock.patch('scripts.launcher.installation.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
                _initial_admin(project, {}, args, {})
            call = run.call_args
            self.assertEqual(call.args[0][0], str(project.python))
            self.assertEqual(call.args[0][-1], 'initial-admin-json')
            self.assertEqual(json.loads(call.kwargs['input']), credential)
            self.assertTrue(call.kwargs['capture_output'])
            self.assertNotIn(credential['password'], str(call.args))
            self.assertNotIn(credential['password'], str(call.kwargs['env']))
            provider.assert_called_once_with()

    def test_private_json_input_is_bounded_and_output_contains_no_credentials(self):
        from scripts.launcher.installation_probe import provision_admin_json
        service = mock.Mock(return_value=True)
        with mock.patch.dict(sys.modules, {'users.initial_admin': SimpleNamespace(create_initial_admin=service)}):
            for value in ('not-json', '{"username":"U12345","password":"x","extra":1}', 'x' * 16385):
                self.assertEqual(provision_admin_json(StringIO(value)),
                                 {'status': 'error', 'code': 'invalid_admin_input'})
            service.assert_not_called()
            self.assertEqual(provision_admin_json(StringIO('{"username":"U12345","password":"transport-fixture"}')),
                             {'status': 'created'})
            service.assert_called_once_with('U12345', 'transport-fixture')
            service.side_effect = RuntimeError('private-diagnostic-fixture')
            self.assertEqual(provision_admin_json(StringIO('{"username":"U12345","password":"transport-fixture"}')),
                             {'status': 'error', 'code': 'invalid_admin_input'})

    def test_existing_administrator_never_requests_gui_credentials(self):
        from scripts.launcher.installation import _initial_admin
        provider = mock.Mock(side_effect=AssertionError('credential request'))
        with mock.patch('scripts.launcher.installation.backend_inspection', return_value={'admin_exists': True}), \
             mock.patch('scripts.launcher.installation.subprocess.run') as run:
            _initial_admin(None, {}, SimpleNamespace(no_admin=False, admin_provider=provider), {})
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
