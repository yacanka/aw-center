"""System Python selection never implicitly downloads a replacement interpreter."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import nullcontext
from contextlib import ExitStack

from scripts.launcher import toolchain
from scripts.launcher.model import LauncherError
from scripts.launcher.installation_sources import SourceSettings, load_catalog
from scripts.manager.operations import arguments
from scripts.manager.view_model import normalize_values


class SystemPythonTests(unittest.TestCase):
    def test_provision_and_later_start_keep_system_selection_without_managed_python(self):
        from scripts.launcher import installation
        from scripts.launcher.installation_profiles import provision_profile, load_profile
        from scripts.test_launcher import create_project
        python = Path(sys.executable).resolve()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as mocks:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            project = create_project(source)
            home = root / 'private'
            profile = provision_profile(project, 'dev', home)
            keys = Path(profile['env_file']).read_bytes()
            args = arguments({'action': 'provision'})
            args.python_executable = python
            mocks.enter_context(patch.object(installation, 'require_windows'))
            mocks.enter_context(patch.object(installation, 'installation_home', return_value=home))
            mocks.enter_context(patch('scripts.launcher.installation_profiles.installation_home', return_value=home))
            mocks.enter_context(patch.object(installation, 'source_settings', return_value=SourceSettings()))
            ensure = mocks.enter_context(patch.object(installation, 'ensure_toolchain', return_value={'AWCENTER_MANAGED_PYTHON': str(python)}))
            dependencies = mocks.enter_context(patch.object(installation, 'install_dependencies'))
            mocks.enter_context(patch.object(installation, '_initialize_schema'))
            mocks.enter_context(patch.object(installation, '_initial_admin'))
            mocks.enter_context(patch.object(installation, '_core_checks', return_value=[]))
            mocks.enter_context(patch('scripts.launcher.installation_features.install_features', return_value=[]))
            installation.provision(project, args)
            self.assertEqual(ensure.call_args.kwargs['python_executable'], python)
            self.assertEqual(dependencies.call_args.kwargs['expected_python'], python)
            self.assertEqual(load_profile(project, 'dev', home)['python_executable'], str(python))
            inspect = mocks.enter_context(patch.object(installation, 'inspect_toolchain', return_value=[{'status': 'ready'}]))
            tools = mocks.enter_context(patch.object(toolchain, 'toolchain_environment', return_value={'AWCENTER_MANAGED_PYTHON': str(python)}))
            mocks.enter_context(patch('scripts.launcher.installation_features.feature_environment', return_value={}))
            mocks.enter_context(patch.object(installation, '_django'))
            mocks.enter_context(patch.object(installation.runtime, 'dev'))
            installation.start_profile(project, 'dev')
            self.assertEqual(inspect.call_args.kwargs['python_executable'], python)
            self.assertEqual(tools.call_args.kwargs['python_executable'], python)
            self.assertEqual(Path(profile['env_file']).read_bytes(), keys)

    def test_discovery_disables_automatic_launcher_installation(self):
        from scripts.launcher.system_python import _probe
        with patch.dict(os.environ, {'PYLAUNCHER_ALLOW_INSTALL': '1', 'PYTHON_MANAGER_AUTOMATIC_INSTALL': 'true'}), \
             patch('scripts.launcher.system_python.controlled_run', return_value=subprocess.CompletedProcess([], 1, '', '')) as run:
            self.assertIsNone(_probe(['py', '-3.11']))
        values = run.call_args.kwargs['env']
        self.assertNotIn('PYLAUNCHER_ALLOW_INSTALL', values)
        self.assertEqual(values['PYTHON_MANAGER_AUTOMATIC_INSTALL'], 'false')

    def test_probe_rejects_wrong_version_bitness_and_implementation(self):
        from scripts.launcher.system_python import _probe
        for changed in ({'version': [3, 12]}, {'bits': 32}, {'implementation': 'pypy'}):
            value = {'version': [3, 11], 'bits': 64, 'implementation': 'cpython', 'base': str(Path(sys.executable).resolve()), **changed}
            with patch('scripts.launcher.system_python.controlled_run', return_value=subprocess.CompletedProcess([], 0, json.dumps(value), '')):
                self.assertIsNone(_probe(['python']))

    def test_windows_arm64_python_is_not_mistaken_for_x64(self):
        from scripts.launcher.system_python import _probe
        value = {'version': [3, 11], 'bits': 64, 'implementation': 'cpython',
                 'platform': 'win-arm64', 'base': str(Path(sys.executable).resolve())}
        with patch.object(sys, 'platform', 'win32'), \
             patch('scripts.launcher.system_python.controlled_run', return_value=subprocess.CompletedProcess([], 0, json.dumps(value), '')):
            self.assertIsNone(_probe(['python']))

    def test_unchecked_frozen_bootstrap_selects_system_python(self):
        from scripts.manager.operations import _bundled_tools
        args = arguments({'action': 'provision'})
        python = Path(sys.executable).resolve()
        with patch.object(sys, 'frozen', True, create=True), \
             patch('scripts.launcher.system_python.discover_python', return_value=python), \
             patch('scripts.launcher.installation_profiles.installation_home', return_value=Path('/private/install')), \
             patch('scripts.launcher.installation_state.installation_lock', return_value=nullcontext()), \
             patch.object(toolchain, 'ensure_toolchain', return_value={}) as ensure:
            _bundled_tools(args, lambda event: None)
        self.assertEqual(ensure.call_args.kwargs['python_executable'], python)
        self.assertEqual(args.python_executable, python)

    def test_checked_bootstrap_does_not_search_for_system_python(self):
        from scripts.manager.operations import _bundled_tools
        args = arguments({'action': 'provision', 'install_python': True})
        with patch('scripts.launcher.system_python.discover_python') as discover, \
             patch('scripts.launcher.installation_profiles.installation_home', return_value=Path('/private/install')), \
             patch('scripts.launcher.installation_state.installation_lock', return_value=nullcontext()), \
             patch.object(toolchain, 'ensure_toolchain', return_value={}):
            _bundled_tools(args, lambda event: None)
        discover.assert_not_called()

    def test_existing_system_toolchain_bundle_does_not_prepare_python_archive(self):
        from scripts.manager.operations import _bundle
        from scripts.test_launcher import create_project
        args = arguments({'action': 'bundle', 'output': '/bundle'})
        python = Path(sys.executable).resolve()
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary).resolve())
            args.progress = lambda _: None
            with patch('scripts.launcher.system_python.discover_python', return_value=python), \
                 patch('scripts.launcher.installation_profiles.installation_home', return_value=Path('/private/install')), \
                 patch.object(toolchain, 'inspect_toolchain', return_value=[{'status': 'ready'}]) as inspect, \
                 patch.object(toolchain, 'toolchain_environment', return_value={}) as env, \
                 patch('scripts.manager.operations._bundled_tools') as prepare, \
                 patch('scripts.launcher.installation.source_settings', return_value=SourceSettings()), \
                 patch('scripts.launcher.installation_bundle.prepare_install_bundle'):
                _bundle(project, args, lambda _: None)
            prepare.assert_not_called()
            self.assertEqual(inspect.call_args.kwargs['python_executable'], python)
            self.assertEqual(env.call_args.kwargs['python_executable'], python)

    def test_runtime_selection_is_profile_scoped_and_preserves_keys(self):
        from scripts.launcher.installation_profiles import provision_profile, load_profile, update_python_runtime
        from scripts.test_launcher import create_project
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            project = create_project(source)
            profile = provision_profile(project, 'dev', root / 'private')
            before = Path(profile['env_file']).read_bytes()
            selected = Path(sys.executable).resolve()
            updated = update_python_runtime(project, profile, selected)
            self.assertEqual(load_profile(project, 'dev', root / 'private')['python_executable'], str(selected))
            self.assertEqual(Path(updated['env_file']).read_bytes(), before)
            restored = update_python_runtime(project, updated, None)
            self.assertNotIn('python_executable', restored)
            self.assertEqual(Path(restored['env_file']).read_bytes(), before)

    def test_existing_venv_cannot_silently_switch_its_base_interpreter(self):
        from scripts.launcher.installation_dependencies import _ensure_venv
        from scripts.test_launcher import create_project
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary).resolve())
            project.python.parent.mkdir(parents=True)
            project.python.write_text('fixture')
            answers = [subprocess.CompletedProcess([], 0, 'True\n', ''),
                       subprocess.CompletedProcess([], 0, str(project.root / 'other-python') + '\n', '')]
            with patch('scripts.launcher.installation_dependencies.capture', side_effect=answers):
                with self.assertRaisesRegex(LauncherError, '.venv'):
                    _ensure_venv(project, {}, expected_python=Path(sys.executable).resolve())

    def test_manager_default_is_system_python_and_checkbox_is_boolean(self):
        self.assertIs(normalize_values('provision', {}).get('install_python'), False)
        self.assertIs(normalize_values('provision', {'install_python': True})['install_python'], True)
        self.assertIs(arguments({'action': 'provision'}).install_python, False)

    def test_system_mode_installs_only_node_and_npm(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            python = Path(sys.executable).resolve()
            with patch('scripts.launcher.system_python.validate_python', return_value=python), \
                 patch.object(toolchain, 'fetch_artifact', side_effect=lambda artifact, *_: home / artifact.filename) as fetch, \
                 patch.object(toolchain, '_install', side_effect=lambda home, artifact, *_args, **_kwargs: home / artifact.name):
                values = toolchain.ensure_toolchain(home, SourceSettings(), python_executable=python)
            self.assertEqual([call.args[0].name for call in fetch.call_args_list], ['node', 'npm'])
            self.assertEqual(values['AWCENTER_MANAGED_PYTHON'], str(python))
            self.assertFalse((home / 'runtimes' / 'python-3.11.18').exists())

    def test_missing_system_python_fails_before_toolchain_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve() / 'not-created'
            with patch('scripts.launcher.system_python.validate_python', side_effect=LauncherError('Python 3.11 x64 bulunamadı')), \
                 patch.object(toolchain, 'fetch_artifact') as fetch:
                with self.assertRaises(LauncherError):
                    toolchain.ensure_toolchain(home, SourceSettings(), python_executable=Path('/missing/python'))
            fetch.assert_not_called()
            self.assertFalse(home.exists())

    def test_system_inspection_does_not_require_managed_python_archive(self):
        from scripts.launcher.system_python import validate_python
        python = Path(sys.executable).resolve()
        with tempfile.TemporaryDirectory() as temporary, \
             patch('scripts.launcher.system_python.validate_python', return_value=python), \
             patch.object(toolchain, '_trusted_inventory', return_value={}), \
             patch.object(toolchain, '_inventory', return_value={}):
            home = Path(temporary).resolve()
            for name, artifact in load_catalog().items():
                if name == 'python':
                    continue
                target = toolchain._directory(home, artifact)
                target.mkdir(parents=True)
                (target / toolchain.RECEIPT).write_text(json.dumps({'name': name, 'version': artifact.version, 'sha256': artifact.sha256}))
            checks = toolchain.inspect_toolchain(home, python_executable=python)
            self.assertTrue(all(check['status'] == 'ready' for check in checks), checks)
            self.assertIn('sistem', checks[0]['detail'].lower())

    def test_installed_interpreter_probe_accepts_real_cpython_311_x64(self):
        from scripts.launcher.system_python import validate_python
        if sys.version_info[:2] != (3, 11):
            self.skipTest('Local test interpreter is not Python 3.11')
        base = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        self.assertEqual(validate_python(base), base)

    def test_incompatible_or_store_alias_python_is_not_accepted(self):
        from scripts.launcher.system_python import discover_python
        with patch('scripts.launcher.system_python._candidates', return_value=[['bad-python']]), \
             patch('scripts.launcher.system_python._probe', return_value=None):
            with self.assertRaisesRegex(LauncherError, '3.11'):
                discover_python()


if __name__ == '__main__':
    unittest.main()
