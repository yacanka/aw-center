"""Manager local settings resolve fresh inputs without adopting runtime output."""
import base64
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.launcher import installation_profiles as profiles
from scripts.launcher.installation_permissions import require_private
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project


class LocalConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / 'source').mkdir()
        self.project = create_project(self.root / 'source')
        self.home = self.root / 'home'
        self.selected = self.root / 'selected.env'
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.location = patch.object(profiles, 'installation_home', return_value=self.home)
        self.location.start()
        self.addCleanup(self.location.stop)

    def args(self, **values):
        return SimpleNamespace(profile='dev', env_file=values.pop('env_file', self.selected),
                               host=values.pop('host', None), backend_port=values.pop('backend_port', None),
                               frontend_port=values.pop('frontend_port', None),
                               automatic_ports=values.pop('automatic_ports', ()), **values)

    def write(self, **values):
        self.selected.write_text(profiles._environment_content(values), encoding='utf-8')
        return self.selected.read_bytes()

    def apply(self, args=None, profile=None):
        from scripts.launcher.installation_local_config import apply_local_configuration
        return apply_local_configuration(self.project, args or self.args(), profile)

    def apply_without_port_probe(self, args=None, profile=None):
        # These persistence tests do not depend on opening local listening ports.
        with patch('scripts.launcher.installation_local_config.select_ports',
                   side_effect=lambda candidate, ports, **_options: {**ports, 'port_modes': candidate['port_modes']}):
            return self.apply(args, profile)

    def test_legacy_database_keys_survive_first_switch_and_return(self):
        legacy = profiles.provision_profile(self.project, 'dev', self.home)
        original = profiles.read_profile_environment(legacy)
        (self.project.backend / 'db.sqlite3').write_bytes(b'synthetic populated legacy database')
        self.write(DATABASE_URL='sqlite:///second.sqlite3')
        second = self.apply_without_port_probe(profile=legacy)
        records = [profiles.read_environment(path) for path in (self.home / 'config/local-keys').iterdir()]
        expected = {key: original[key] for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY')}
        self.assertTrue(any(record == expected for record in records), 'Previous database keys were not retained')
        self.write(DATABASE_URL='sqlite:///db.sqlite3')
        restored = self.apply_without_port_probe(profile=second)
        values = profiles.read_profile_environment(restored)
        for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY'):
            self.assertTrue(values[key] == original[key], key + ' changed after returning to the original database')

    def test_failed_legacy_key_preservation_does_not_replace_current_environment(self):
        legacy = profiles.provision_profile(self.project, 'dev', self.home)
        original = Path(legacy['env_file']).read_bytes()
        self.write(DATABASE_URL='sqlite:///second.sqlite3')
        write = profiles._write_new
        def fail_key_record(path, content):
            if path.parent.name == 'local-keys':
                raise OSError('synthetic key publication failure')
            return write(path, content)
        with patch.object(profiles, '_write_new', side_effect=fail_key_record), self.assertRaises(OSError):
            self.apply_without_port_probe(profile=legacy)
        self.assertTrue(Path(legacy['env_file']).read_bytes() == original, 'Current environment was replaced')
        self.assertEqual(profiles.load_profile(self.project, 'dev', self.home), legacy)

    def test_interrupted_legacy_switch_recovers_without_losing_previous_keys(self):
        legacy = profiles.provision_profile(self.project, 'dev', self.home)
        original = profiles.read_profile_environment(legacy)
        (self.project.backend / 'db.sqlite3').write_bytes(b'synthetic populated legacy database')
        self.write(DATABASE_URL='sqlite:///second.sqlite3')
        replace = profiles._write_replace
        def interrupt(path, content):
            if path.name == 'dev.profile.json':
                raise OSError('synthetic profile publication interruption')
            return replace(path, content)
        with patch.object(profiles, '_write_replace', side_effect=interrupt), self.assertRaises(OSError):
            self.apply_without_port_probe(profile=legacy)
        recovered = profiles.provision_profile(self.project, 'dev', self.home)
        self.write(DATABASE_URL='sqlite:///db.sqlite3')
        restored = self.apply_without_port_probe(profile=recovered)
        values = profiles.read_profile_environment(restored)
        for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY'):
            self.assertTrue(values[key] == original[key], key + ' changed after recovery')

    def test_old_pending_switch_preserves_readable_legacy_keys_before_recovery(self):
        legacy = profiles.provision_profile(self.project, 'dev', self.home)
        original = profiles.read_profile_environment(legacy)
        (self.project.backend / 'db.sqlite3').write_bytes(b'synthetic populated legacy database')
        self.write(DATABASE_URL='sqlite:///second.sqlite3')
        replace = profiles._write_replace
        def interrupt(path, content):
            if path.name == 'dev.env':
                raise OSError('synthetic interruption before environment publication')
            return replace(path, content)
        with patch.object(profiles, '_write_replace', side_effect=interrupt), self.assertRaises(OSError):
            self.apply_without_port_probe(profile=legacy)
        # Recreate a pending operation written by the earlier implementation,
        # which did not save the still-readable legacy snapshot's key record.
        for record in (self.home / 'config/local-keys').iterdir():
            record.unlink()
        recovered = profiles.provision_profile(self.project, 'dev', self.home)
        self.write(DATABASE_URL='sqlite:///db.sqlite3')
        restored = self.apply_without_port_probe(profile=recovered)
        values = profiles.read_profile_environment(restored)
        for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY'):
            self.assertTrue(values[key] == original[key], key + ' changed during legacy journal recovery')

    def test_state_path_history_keeps_legacy_and_new_outputs_across_return(self):
        legacy = profiles.provision_profile(self.project, 'dev', self.home)
        (self.project.backend / 'db.sqlite3').write_bytes(b'synthetic populated legacy database')
        self.selected = self.project.backend / '.env.second'
        source = self.write(DATABASE_URL='sqlite:///second.sqlite3', PRIVATE_MEDIA_ROOT='second-private',
                            CACHE_DIRECTORY='second-cache', STATIC_ROOT='second-static', MEDIA_ROOT='second-media',
                            MODEL_RUNTIME_DIR='second-models', CUSTOM_TEMPLATE_DIR='second-templates',
                            COVER_PAGE_TEMPLATE_PATH='second-cover.docx')
        second = self.apply_without_port_probe(profile=legacy)
        history = second['local_configuration'].get('state_paths', {})
        self.assertTrue({'backend/db.sqlite3', 'backend/db.sqlite3-wal', 'backend/db.sqlite3-shm',
                         'backend/db.sqlite3-journal', 'backend/second.sqlite3', 'backend/second.sqlite3-wal',
                         'backend/second.sqlite3-shm', 'backend/second.sqlite3-journal',
                         'backend/.env.second', 'backend/second-cover.docx'}.issubset(history.get('files', [])))
        self.assertTrue({'backend/private_media', 'backend/second-private', 'backend/second-cache',
                         'backend/second-static', 'backend/second-media', 'backend/second-models',
                         'backend/second-templates'}.issubset(history.get('directories', [])))
        restored = self.apply_without_port_probe(self.args(env_file=None), second)
        self.assertEqual(restored['local_configuration']['state_paths'], history)
        self.assertEqual(self.selected.read_bytes(), source)

    def test_selected_environment_history_survives_switch_and_clear(self):
        self.selected = self.project.backend / 'first.env'
        first_source = self.write()
        first = self.apply_without_port_probe()
        first_path = self.selected
        self.selected = self.project.backend / '.env.second'
        second_source = self.write()
        second = self.apply_without_port_probe(profile=first)
        cleared = self.apply_without_port_probe(self.args(env_file=None), second)
        files = cleared['local_configuration'].get('state_paths', {}).get('files', [])
        self.assertIn('backend/first.env', files)
        self.assertIn('backend/.env.second', files)
        self.assertEqual(first_path.read_bytes(), first_source)
        self.assertEqual(self.selected.read_bytes(), second_source)

    def test_state_path_metadata_rejects_traversal_duplicates_and_unbounded_inputs(self):
        from scripts.launcher.installation_local_config import resolve_local_configuration
        self.write()
        profile, _values = resolve_local_configuration(self.project, self.args())
        invalid = ({'files': ['../outside.env'], 'directories': []},
                   {'files': ['/absolute.env'], 'directories': []},
                   {'files': ['backend/./selected.env'], 'directories': []},
                   {'files': ['backend\\selected.env'], 'directories': []},
                   {'files': ['backend/a.env', 'BACKEND/A.ENV'], 'directories': []},
                   {'files': ['backend/a.env'], 'directories': '.',},
                   {'files': ['backend/' + 'x' * 4096], 'directories': []},
                   {'files': [f'backend/{index}.env' for index in range(1025)], 'directories': []})
        for paths in invalid:
            candidate = {**profile, 'local_configuration': {**profile['local_configuration'], 'state_paths': paths}}
            with self.subTest(paths=paths), self.assertRaises(LauncherError):
                profiles._validate_options(candidate)

    def test_state_path_metadata_accepts_older_marker_and_skips_executable_source(self):
        from scripts.launcher.installation_local_config import resolve_local_configuration
        self.selected = self.project.backend / 'selected.py'
        self.write()
        profile, _values = resolve_local_configuration(self.project, self.args())
        self.assertNotIn('backend/selected.py', profile['local_configuration'].get('state_paths', {}).get('files', []))
        marker = dict(profile['local_configuration'])
        marker.pop('state_paths', None)
        profiles._validate_options({**profile, 'local_configuration': marker})

    def test_manifest_owned_selected_source_is_not_an_output_exemption(self):
        from scripts.launcher.installation_local_config import resolve_local_configuration
        self.selected = self.project.backend / 'owned.env'
        self.write(DATABASE_URL='sqlite:///owned.sqlite3')
        # Path classification reads names only. The caller still verifies the
        # complete source manifest and bytes before accepting the candidate.
        manifest = {'artifacts': [{'path': 'backend/owned.env'}, {'path': 'backend/owned.sqlite3'}]}
        (self.project.root / 'manager-source-manifest.json').write_text(json.dumps(manifest))
        profile, _values = resolve_local_configuration(self.project, self.args())
        files = profile['local_configuration']['state_paths']['files']
        self.assertNotIn('backend/owned.env', files)
        self.assertIn('backend/owned.sqlite3', files)

    def test_executable_dotenv_names_are_not_source_exemptions(self):
        from scripts.launcher.installation_local_config import resolve_local_configuration
        for name in ('.env.py', '.env.pth', '.env.cmd'):
            self.selected = self.project.backend / name
            self.write()
            profile, _values = resolve_local_configuration(self.project, self.args())
            with self.subTest(name=name):
                self.assertNotIn('backend/' + name, profile['local_configuration']['state_paths']['files'])

    def test_manager_overrides_then_clearing_falls_through_to_fresh_source(self):
        self.write(DEV_BACKEND_PORT='18300', DEV_FRONTEND_PORT='15300', EMAIL_HOST='first.example.invalid')
        original = self.selected.read_bytes()
        profile = self.apply(self.args(backend_port=18301))
        self.assertEqual(profile['backend_port'], 18301)
        self.assertEqual(profile['frontend_port'], 15300)
        self.assertEqual(profile['local_configuration']['overrides'], {'backend_port': 18301})
        self.assertEqual(self.selected.read_bytes(), original)
        self.write(DEV_BACKEND_PORT='18302', DEV_FRONTEND_PORT='15302', EMAIL_HOST='second.example.invalid')
        updated = self.apply(self.args(), profile)
        self.assertEqual(updated['backend_port'], 18302)
        self.assertEqual(profiles.read_profile_environment(updated)['EMAIL_HOST'], 'second.example.invalid')
        self.assertEqual(updated['local_configuration']['overrides'], {})

    def test_clearing_source_removes_old_settings_and_preserves_matching_database_keys(self):
        self.write(EMAIL_HOST='source.example.invalid')
        profile = self.apply()
        before = profiles.read_profile_environment(profile)
        updated = self.apply(self.args(env_file=None), profile)
        after = profiles.read_profile_environment(updated)
        self.assertNotIn('EMAIL_HOST', after)
        self.assertEqual(after['SECRET_KEY'], before['SECRET_KEY'])
        self.assertEqual(after['JIRA_SESSION_ENCRYPTION_KEY'], before['JIRA_SESSION_ENCRYPTION_KEY'])

    def test_preparation_reports_environment_only_update_without_promoting_raw_inputs(self):
        from scripts.manager.ensure import prepare_connection
        self.write(EMAIL_HOST='first.example.invalid')
        self.apply()
        self.write(EMAIL_HOST='second.example.invalid')
        args = self.args()
        self.assertTrue(prepare_connection(self.project, args))
        self.assertIsNone(args.backend_port)
        self.assertIsNone(args.frontend_port)
        self.assertIsNone(args.host)

    def test_relative_database_and_application_paths_use_backend_cwd(self):
        self.write(DATABASE_URL='sqlite:///custom.sqlite3', PRIVATE_MEDIA_ROOT='custom-private',
                   CACHE_DIRECTORY='custom-cache', MODEL_RUNTIME_DIR='models', CUSTOM_TEMPLATE_DIR='templates',
                   WORD_ANALYZER_BI_MODEL='special-model', COVER_PAGE_TEMPLATE_PATH='special.docx')
        content = self.selected.read_bytes()
        profile = self.apply()
        values = profiles.read_profile_environment(profile)
        self.assertEqual(values['DATABASE_URL'], 'sqlite:///' + (self.project.backend / 'custom.sqlite3').as_posix())
        for key, relative in {'PRIVATE_MEDIA_ROOT': 'custom-private', 'CACHE_DIRECTORY': 'custom-cache',
                              'MODEL_RUNTIME_DIR': 'models', 'CUSTOM_TEMPLATE_DIR': 'templates',
                              'WORD_ANALYZER_BI_MODEL': 'special-model', 'COVER_PAGE_TEMPLATE_PATH': 'special.docx'}.items():
            self.assertEqual(values[key], (self.project.backend / relative).as_posix())
        self.assertEqual(self.selected.read_bytes(), content)
        self.assertEqual(profiles.load_profile(self.project, 'dev', self.home), profile)

    def test_database_private_and_asset_paths_cannot_be_in_replaced_package_trees(self):
        roots = (self.project.venv, self.project.frontend / 'node_modules', self.project.frontend / 'dist',
                 self.project.root / '.runtime/npm-backups', self.project.root / '.runtime/venv-backups',
                 self.project.root / '.runtime/frontend-build-backups')
        for root in roots:
            for key in ('DATABASE_URL', 'PRIVATE_MEDIA_ROOT', 'MODEL_RUNTIME_DIR', 'CUSTOM_TEMPLATE_DIR'):
                value = (root / 'local-state').as_posix()
                self.write(**{key: 'sqlite:///' + value if key == 'DATABASE_URL' else value})
                with self.subTest(root=root, key=key), self.assertRaises(LauncherError):
                    self.apply()
                self.assertFalse(self.home.exists())

    def test_env_source_in_mutable_package_tree_is_rejected_before_creation(self):
        source = self.project.frontend / 'node_modules/local.env'
        source.parent.mkdir()
        source.write_text('EMAIL_HOST=source.example.invalid\n')
        original = source.read_bytes()
        with self.assertRaises(LauncherError):
            self.apply(self.args(env_file=source))
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(self.home.exists())

    def test_normal_runtime_model_and_template_paths_are_accepted(self):
        self.write(MODEL_RUNTIME_DIR='../.runtime/ai-models', CUSTOM_TEMPLATE_DIR='../.runtime/document-templates')
        profile = self.apply()
        values = profiles.read_profile_environment(profile)
        self.assertEqual(values['MODEL_RUNTIME_DIR'], (self.project.root / '.runtime/ai-models').as_posix())
        self.assertEqual(values['CUSTOM_TEMPLATE_DIR'], (self.project.root / '.runtime/document-templates').as_posix())

    def test_source_origins_and_custom_urls_survive_manager_port_override(self):
        self.write(CSRF_TRUSTED_ORIGINS='https://additional.example.invalid',
                   DEV_SERVER_ORIGINS='https://ui.example.invalid',
                   FRONTEND_RESET_URL='https://account.example.invalid/reset')
        profile = self.apply(self.args(frontend_port=15307))
        values = profiles.read_profile_environment(profile)
        self.assertIn('http://localhost:15307', values['CSRF_TRUSTED_ORIGINS'])
        self.assertIn('https://additional.example.invalid', values['CSRF_TRUSTED_ORIGINS'])
        self.assertIn('https://ui.example.invalid', values['DEV_SERVER_ORIGINS'])
        self.assertEqual(values['FRONTEND_RESET_URL'], 'https://account.example.invalid/reset')

    def test_source_keys_are_authoritative_and_database_switches_do_not_reuse_them(self):
        self.write(DATABASE_URL='sqlite:///first.sqlite3')
        first = self.apply()
        first_values = profiles.read_profile_environment(first)
        (self.project.backend / 'first.sqlite3').write_bytes(b'existing fixture')
        self.write(DATABASE_URL='sqlite:///second.sqlite3')
        second = self.apply(profile=first)
        second_values = profiles.read_profile_environment(second)
        self.assertNotEqual(first_values['SECRET_KEY'], second_values['SECRET_KEY'])
        self.assertNotEqual(first_values['JIRA_SESSION_ENCRYPTION_KEY'], second_values['JIRA_SESSION_ENCRYPTION_KEY'])
        self.write(DATABASE_URL='sqlite:///first.sqlite3')
        restored = self.apply(profile=second)
        restored_values = profiles.read_profile_environment(restored)
        self.assertEqual(first_values['SECRET_KEY'], restored_values['SECRET_KEY'])
        self.assertEqual(first_values['JIRA_SESSION_ENCRYPTION_KEY'], restored_values['JIRA_SESSION_ENCRYPTION_KEY'])
        self.write(DATABASE_URL='sqlite:///first.sqlite3', SECRET_KEY='synthetic-source-key',
                   JIRA_SESSION_ENCRYPTION_KEY=base64.urlsafe_b64encode(b'x' * 32).decode())
        updated = self.apply(profile=restored)
        self.assertEqual(profiles.read_profile_environment(updated)['SECRET_KEY'], 'synthetic-source-key')
        for path in (self.home / 'config/local-keys').iterdir():
            require_private(path)

    def test_unknown_existing_effective_database_missing_keys_is_rejected_without_writes(self):
        database = self.project.backend / 'foreign.sqlite3'
        database.write_bytes(b'foreign fixture')
        self.write(DATABASE_URL='sqlite:///foreign.sqlite3')
        with self.assertRaises(LauncherError) as caught:
            self.apply()
        self.assertNotIn('foreign.sqlite3', str(caught.exception))
        self.assertEqual(database.read_bytes(), b'foreign fixture')
        self.assertFalse(self.home.exists())

    def test_resolving_is_read_only_and_selected_port_is_manual(self):
        from scripts.launcher.installation_local_config import resolve_local_configuration
        self.write(PORT='18310', DEV_FRONTEND_PORT='15310')
        profile, _values = resolve_local_configuration(self.project, self.args())
        self.assertEqual(profile['port_modes'], {'backend_port': 'manual', 'frontend_port': 'manual'})
        self.assertFalse(self.home.exists())

    def test_apply_creates_only_missing_database_parent_directories(self):
        from scripts.launcher.installation_local_config import resolve_local_configuration
        existing_mode = self.project.backend.stat().st_mode
        self.write(DATABASE_URL='sqlite:///new-state/nested/local.sqlite3')
        resolve_local_configuration(self.project, self.args())
        self.assertFalse((self.project.backend / 'new-state').exists())
        profile = self.apply()
        database = Path(profiles.read_profile_environment(profile)['DATABASE_URL'].removeprefix('sqlite:///'))
        self.assertFalse(database.exists())
        require_private(database.parent)
        require_private(database.parent.parent)
        self.assertEqual(self.project.backend.stat().st_mode, existing_mode)

    def test_explicit_auto_overrides_occupied_source_port(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            self.write(DEV_BACKEND_PORT=str(port))
            with self.assertRaises(LauncherError):
                self.apply()
            profile = self.apply(self.args(automatic_ports=('backend_port',)))
            self.assertNotEqual(profile['backend_port'], port)
            self.assertEqual(profile['port_modes']['backend_port'], 'automatic')

    def test_invalid_sources_do_not_create_local_profile(self):
        for key, value in (('DATABASE_URL', 'postgres://invalid/invalid'),
                           ('PYTHONPATH', '/invalid-code'), ('IPV4_ADDRESS', 'bad-host'),
                           ('DEV_BACKEND_PORT', 'invalid-port')):
            self.write(**{key: value})
            with self.subTest(key=key), self.assertRaises(LauncherError):
                self.apply()
            self.assertFalse(self.home.exists())

    def test_generated_runtime_copy_cannot_be_selected_as_immutable_source(self):
        self.write()
        profile = self.apply()
        runtime = Path(profile['env_file'])
        original = runtime.read_bytes()
        with self.assertRaises(LauncherError) as caught:
            self.apply(self.args(env_file=runtime, backend_port=18319), profile)
        self.assertEqual(getattr(caught.exception, 'code', None), 'env_runtime_source_invalid')
        self.assertEqual(getattr(caught.exception, 'field', None), 'env_file')
        self.assertEqual(runtime.read_bytes(), original)
        self.assertNotIn(str(runtime), str(caught.exception))

    def test_private_key_record_cannot_be_selected_as_immutable_source(self):
        self.write()
        profile = self.apply()
        record = next((self.home / 'config/local-keys').iterdir())
        original = record.read_bytes()
        with self.assertRaises(LauncherError) as caught:
            self.apply(self.args(env_file=record), profile)
        self.assertEqual(getattr(caught.exception, 'code', None), 'env_runtime_source_invalid')
        self.assertEqual(record.read_bytes(), original)

    def test_self_reference_is_rejected_before_pending_recovery_can_change_source(self):
        from scripts.manager.ensure import prepare_connection
        self.write()
        profile = self.apply()
        runtime = Path(profile['env_file'])
        original = runtime.read_bytes()
        self.write(EMAIL_HOST='pending.example.invalid')
        replace = profiles._write_replace
        def interrupt(path, content):
            if path.name == 'dev.env':
                raise OSError('synthetic interruption before env publication')
            return replace(path, content)
        with patch.object(profiles, '_write_replace', side_effect=interrupt), self.assertRaises(OSError):
            self.apply(profile=profile)
        with self.assertRaises(LauncherError):
            prepare_connection(self.project, self.args(env_file=runtime))
        self.assertEqual(runtime.read_bytes(), original)
        self.assertTrue((self.home / 'config/dev.pending.json').exists())

    def test_asset_rebind_preserves_explicit_source_model_paths(self):
        self.write(MODEL_RUNTIME_DIR='models', CUSTOM_TEMPLATE_DIR='templates',
                   WORD_ANALYZER_BI_MODEL='special-model')
        profile = self.apply()
        before = profiles.read_profile_environment(profile)
        updated = profiles.update_asset_set(self.project, profile, 'next-set')
        after = profiles.read_profile_environment(updated)
        for key in ('MODEL_RUNTIME_DIR', 'CUSTOM_TEMPLATE_DIR', 'WORD_ANALYZER_BI_MODEL'):
            self.assertEqual(after[key], before[key])

    def test_asset_rebind_keeps_implicit_children_below_selected_model_root(self):
        self.write(MODEL_RUNTIME_DIR='models', CUSTOM_TEMPLATE_DIR='templates')
        profile = self.apply()
        updated = profiles.update_asset_set(self.project, profile, 'next-set')
        after = profiles.read_profile_environment(updated)
        self.assertEqual(after['WORD_ANALYZER_BI_MODEL'], (self.project.backend / 'models/paraphrase-multilingual').as_posix())
        self.assertEqual(after['COVER_PAGE_TEMPLATE_PATH'], (self.project.backend / 'templates/cover_page_template.docx').as_posix())

    def test_unchanged_automatic_port_hint_remains_stable_when_default_is_busy(self):
        from scripts.launcher.installation_local_config import configuration_changed
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 8000))
            self.write()
            profile = self.apply()
            self.assertNotEqual(profile['backend_port'], 8000)
            self.assertFalse(configuration_changed(self.project, self.args(), profile))
            updated = self.apply(profile=profile)
            self.assertEqual(updated['backend_port'], profile['backend_port'])

    def test_main_action_reselects_occupied_existing_automatic_port_under_preparation(self):
        from scripts.launcher import installation, runtime
        from scripts.manager import operations
        self.write()
        profile = self.apply()
        launched, prepared, events = [], [], []
        def start(project, name, *, on_ready, on_health):
            current = profiles.load_profile(project, name, self.home)
            runtime.require_port(current['host'], current['backend_port'])
            launched.append(current)
            on_ready(current)
        def provision(project, args):
            prepared.append(args.profile)
            return []
        ready = [{'name': 'core', 'status': 'ready'}]
        with socket.socket() as listener:
            listener.bind((profile['host'], profile['backend_port']))
            listener.listen()
            with patch.object(operations, '_project_for', return_value=self.project), \
                 patch.object(installation, 'start_profile', side_effect=start), \
                 patch.object(installation, 'provision', side_effect=provision), \
                 patch.object(installation, '_core_checks', return_value=ready), \
                 patch('scripts.launcher.toolchain.inspect_toolchain', return_value=ready):
                operations.execute({'action': 'ensure', 'source_root': str(self.project.root),
                                    'env_file': str(self.selected)}, events.append,
                                   lambda: None, threading.Event())
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(len(launched), 1)
        self.assertNotEqual(launched[0]['backend_port'], profile['backend_port'])
        self.assertEqual(launched[0]['local_configuration']['overrides'], {})
        self.assertEqual(prepared, [])

    def test_model_directory_is_accepted_and_file_in_its_place_is_rejected(self):
        directory = self.project.backend / 'model'
        directory.mkdir()
        self.write(WORD_ANALYZER_BI_MODEL='model')
        profile = self.apply()
        self.assertEqual(profiles.read_profile_environment(profile)['WORD_ANALYZER_BI_MODEL'], directory.as_posix())
        file = self.project.backend / 'not-model'
        file.touch()
        self.write(WORD_ANALYZER_BI_MODEL='not-model')
        with self.assertRaises(LauncherError):
            self.apply(profile=profile)

    def test_invalid_key_record_never_leaks_selected_values(self):
        self.write()
        profile = self.apply()
        record = next((self.home / 'config/local-keys').iterdir())
        record.write_text('SECRET_KEY=synthetic-private-value\n')
        with self.assertRaises(LauncherError) as caught:
            self.apply(profile=profile)
        self.assertNotIn('synthetic-private-value', str(caught.exception))

    def test_local_marker_cannot_relax_production_or_unknown_versions(self):
        self.write()
        profile = self.apply()
        candidate = {**profile, 'name': 'prod'}
        with self.assertRaises(LauncherError):
            profiles._validate_options(candidate)
        candidate = {**profile, 'local_configuration': {**profile['local_configuration'], 'version': 99}}
        with self.assertRaises(LauncherError):
            profiles._validate_options(candidate)

    def test_interrupted_local_update_recovers_without_rereading_changed_source(self):
        self.write(EMAIL_HOST='first.example.invalid')
        profile = self.apply()
        self.write(EMAIL_HOST='second.example.invalid')
        replace = profiles._write_replace
        def interrupt(path, content):
            if path.name == 'dev.env':
                raise OSError('synthetic publication interruption')
            return replace(path, content)
        with patch.object(profiles, '_write_replace', side_effect=interrupt), self.assertRaises(OSError):
            self.apply(profile=profile)
        self.write(EMAIL_HOST='third.example.invalid')
        home, path, env = profiles._paths(self.project, 'dev', self.home)
        profiles._recover_pending(self.project, 'dev', home, path, env, path.with_name('dev.pending.json'))
        recovered = profiles.load_profile(self.project, 'dev', self.home)
        self.assertEqual(profiles.read_profile_environment(recovered)['EMAIL_HOST'], 'second.example.invalid')
        self.assertFalse(path.with_name('dev.pending.json').exists())

    def test_interrupted_first_creation_recovers_keys_before_runtime_copy_is_published(self):
        self.write()
        write = profiles._write_new
        def interrupt(path, content):
            if path.name == 'dev.env':
                raise OSError('synthetic first publication interruption')
            return write(path, content)
        with patch.object(profiles, '_write_new', side_effect=interrupt), self.assertRaises(OSError):
            self.apply()
        pending = self.home / 'config/dev.pending.json'
        expected = json.loads(pending.read_text())['environment']['SECRET_KEY']
        self.selected.unlink()
        recovered = profiles.provision_profile(self.project, 'dev', self.home)
        self.assertEqual(profiles.read_profile_environment(recovered)['SECRET_KEY'], expected)
        self.assertFalse(pending.exists())

    def assert_apply_recovers_before_reporting_source_error(self, *, first_creation, missing_source):
        if not first_creation:
            self.write(EMAIL_HOST='initial.example.invalid')
            self.apply_without_port_probe()
        self.write(EMAIL_HOST='recorded.example.invalid')
        method = '_write_new' if first_creation else '_write_replace'
        write = getattr(profiles, method)
        def interrupt(path, content):
            if path.name == 'dev.env':
                raise OSError('synthetic interruption before environment publication')
            return write(path, content)
        with patch.object(profiles, method, side_effect=interrupt), self.assertRaises(OSError):
            self.apply_without_port_probe()
        pending = self.home / 'config/dev.pending.json'
        document = json.loads(pending.read_text())
        expected = document['environment']
        if missing_source:
            self.selected.unlink()
        else:
            self.selected.write_text('invalid dotenv syntax\n')
        with self.assertRaises(profiles.EnvironmentImportError) as caught:
            self.apply_without_port_probe()
        self.assertEqual(caught.exception.code, 'env_file_invalid')
        self.assertFalse(pending.exists(), 'Recorded recovery was blocked by the current source')
        recovered = profiles.load_profile(self.project, 'dev', self.home)
        self.assertEqual(recovered, document['profile'])
        values = profiles.read_profile_environment(recovered)
        self.assertTrue(values == expected, 'Recovered environment differs from the recorded candidate')
        records = [profiles.read_environment(path) for path in (self.home / 'config/local-keys').iterdir()]
        keys = {key: expected[key] for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY')}
        self.assertTrue(any(record == keys for record in records), 'Recorded database keys were not retained')
        if missing_source:
            self.assertFalse(self.selected.exists())
        else:
            self.assertEqual(self.selected.read_text(), 'invalid dotenv syntax\n')

    def test_apply_recovers_first_creation_before_reporting_deleted_source(self):
        self.assert_apply_recovers_before_reporting_source_error(first_creation=True, missing_source=True)

    def test_apply_recovers_first_creation_before_reporting_invalid_source(self):
        self.assert_apply_recovers_before_reporting_source_error(first_creation=True, missing_source=False)

    def test_apply_recovers_update_before_reporting_deleted_source(self):
        self.assert_apply_recovers_before_reporting_source_error(first_creation=False, missing_source=True)

    def test_apply_recovers_update_before_reporting_invalid_source(self):
        self.assert_apply_recovers_before_reporting_source_error(first_creation=False, missing_source=False)

    def assert_managed_metadata_source_blocks_recovery(self, name):
        self.write()
        profile = self.apply_without_port_probe()
        environment = Path(profile['env_file'])
        original = environment.read_bytes()
        replace = profiles._write_replace
        def interrupt(path, content):
            if path.name == 'dev.env':
                raise OSError('synthetic interruption before environment publication')
            return replace(path, content)
        with patch.object(profiles, '_write_replace', side_effect=interrupt), self.assertRaises(OSError):
            self.apply_without_port_probe(self.args(backend_port=18321), profile)
        pending = self.home / 'config/dev.pending.json'
        source = self.home / 'config' / name
        source_content = source.read_bytes()
        with self.assertRaises(profiles.EnvironmentImportError) as caught:
            self.apply_without_port_probe(self.args(env_file=source))
        self.assertEqual(caught.exception.code, 'env_runtime_source_invalid')
        self.assertTrue(pending.exists(), 'Recovery removed the selected metadata source')
        self.assertTrue(source.read_bytes() == source_content, 'Recovery changed the selected metadata source')
        self.assertTrue(environment.read_bytes() == original, 'Recovery changed the runtime copy')

    def test_pending_metadata_source_is_rejected_before_recovery(self):
        self.assert_managed_metadata_source_blocks_recovery('dev.pending.json')

    def test_profile_metadata_source_is_rejected_before_recovery(self):
        self.assert_managed_metadata_source_blocks_recovery('dev.profile.json')

    def test_interrupted_update_rejects_operator_modified_snapshot(self):
        self.write()
        profile = self.apply()
        self.write(EMAIL_HOST='changed.example.invalid')
        replace = profiles._write_replace
        def interrupt(path, content):
            if path.name == 'dev.profile.json':
                raise OSError('synthetic metadata publication interruption')
            return replace(path, content)
        with patch.object(profiles, '_write_replace', side_effect=interrupt), self.assertRaises(OSError):
            self.apply(profile=profile)
        env = Path(profile['env_file'])
        env.write_text(env.read_text() + '# operator modification\n')
        before = env.read_bytes()
        with self.assertRaises(LauncherError):
            profiles.provision_profile(self.project, 'dev', self.home)
        self.assertEqual(env.read_bytes(), before)
