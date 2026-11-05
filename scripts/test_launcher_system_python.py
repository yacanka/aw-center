"""System Python selection never implicitly downloads a replacement interpreter."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
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
    def test_slow_valid_python_is_not_rejected_after_five_seconds(self):
        from scripts.launcher import system_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        original_run = system_python.controlled_run
        calls = []
        def slow_start(command, **options):
            calls.append(command)
            # Model a cold interpreter/module load that exceeds the old budget.
            command = [*command[:-1], 'import time; time.sleep(5.2)\n' + command[-1]]
            return original_run(command, **options)
        with patch.object(system_python, 'controlled_run', side_effect=slow_start):
            self.assertEqual(system_python.discover_python(str(python)), python)
        self.assertEqual(len(calls), 1, 'A fully validated direct interpreter must not be launched twice')

    def test_duplicate_interpreter_aliases_do_not_repeat_timeout(self):
        from scripts.launcher import system_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        # Lexically different spellings can identify the same executable.
        alternate = str(python.parent) + '/../' + python.parent.name + '/' + python.name
        with patch.object(system_python, '_candidates', return_value=[[str(python)], [alternate]]), \
             patch.object(system_python, 'controlled_run', side_effect=subprocess.TimeoutExpired('private command', 60)) as run:
            with self.assertRaises(system_python.SystemPythonError) as caught:
                system_python.discover_python()
        self.assertEqual(caught.exception.code, 'system_python_timeout')
        self.assertEqual(run.call_count, 1)

    def test_extended_probe_can_still_be_cancelled(self):
        from scripts.launcher import process, system_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        stop = threading.Event()
        timer = threading.Timer(0.2, stop.set)
        timer.start()
        try:
            with process.operation_control(stop), patch.object(system_python, '_PROBE', 'import time; time.sleep(30)'):
                with self.assertRaises(process.OperationCancelled):
                    system_python.discover_python(str(python))
        finally:
            timer.cancel()

    def test_wrapper_hint_still_requires_validation_of_actual_base(self):
        from scripts.launcher import system_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        value = {'version': [3, 11], 'bits': 64, 'implementation': 'cpython',
                 'platform': 'win-amd64', 'base': str(python),
                 'modules': {'sysconfig': 'ok', 'venv': 'ok', 'ensurepip': 'ok'}}
        with tempfile.TemporaryDirectory() as temporary:
            hint = Path(temporary).resolve() / 'python-hint.exe'
            hint.write_text('fixture', encoding='utf-8')
            answers = [subprocess.CompletedProcess([], 0, json.dumps(value), ''),
                       subprocess.CompletedProcess([], 0, json.dumps({**value, 'version': [3, 12]}), '')]
            with patch.object(system_python, 'controlled_run', side_effect=answers):
                with self.assertRaises(system_python.SystemPythonError) as caught:
                    system_python.discover_python(str(hint))
        self.assertEqual(caught.exception.code, 'system_python_version')

    def test_manager_reports_python_check_before_waiting_for_probe(self):
        from scripts.manager.operations import _python_choice
        from scripts.launcher.system_python import PROBE_TIMEOUT_SECONDS
        args = arguments({'action': 'provision'})
        phases = []
        args.progress = phases.append
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        def discover():
            self.assertTrue(phases, 'The UI must identify the phase before a slow probe starts')
            return python
        with patch('scripts.launcher.system_python.discover_python', side_effect=discover):
            self.assertEqual(_python_choice(args), {'python_executable': python})
        self.assertIn(str(PROBE_TIMEOUT_SECONDS), phases[0])

    def test_windows_python_3113_is_accepted(self):
        from scripts.launcher.system_python import discover_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        value = {'version': [3, 11], 'micro': 3, 'bits': 64, 'implementation': 'cpython',
                 'platform': 'win-amd64', 'base': str(python),
                 'modules': {'sysconfig': 'ok', 'venv': 'ok', 'ensurepip': 'ok'}}
        with patch.object(sys, 'platform', 'win32'), \
             patch('scripts.launcher.system_python.controlled_run', return_value=subprocess.CompletedProcess([], 0, json.dumps(value), '')):
            self.assertEqual(discover_python(str(python)), python)

    def test_missing_ensurepip_is_reported_instead_of_python_not_found(self):
        from scripts.launcher import system_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        value = {'version': [3, 11], 'micro': 3, 'bits': 64, 'implementation': 'cpython',
                 'platform': 'win-amd64', 'base': str(python),
                 'modules': {'sysconfig': 'ok', 'venv': 'ok', 'ensurepip': 'missing'}}
        with patch.object(system_python, 'controlled_run', return_value=subprocess.CompletedProcess([], 0, json.dumps(value), '')):
            with self.assertRaises(system_python.SystemPythonError) as caught:
                system_python.discover_python(str(python))
        self.assertEqual(caught.exception.code, 'system_python_ensurepip_missing')
        self.assertIn('ensurepip', str(caught.exception))

    def test_start_failure_keeps_numeric_error_without_private_payload(self):
        from scripts.launcher import system_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        error = OSError(13, 'sensitive-file-path password=private-value')
        error.winerror = 193
        with patch.object(system_python, 'controlled_run', side_effect=error):
            with self.assertRaises(system_python.SystemPythonError) as caught:
                system_python.discover_python(str(python))
        self.assertEqual(caught.exception.code, 'system_python_start_failed')
        self.assertIn('193', str(caught.exception))
        self.assertNotIn('sensitive-file-path', str(caught.exception))
        self.assertNotIn('private-value', str(caught.exception))

    def test_manager_error_report_preserves_python_probe_failure(self):
        from scripts.launcher import system_python
        from scripts.manager.operations import execute
        from threading import Event
        events = []
        failure = system_python.SystemPythonError('ensurepip_missing')
        with patch('scripts.manager.operations._dispatch', side_effect=failure):
            execute({'action': 'provision'}, events.append, lambda: None, Event())
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'system_python_ensurepip_missing')
        self.assertIn('ensurepip', error['message'])
        self.assertIn('pip', error['remedy'])

    def test_real_probe_reports_missing_modules_and_import_failures(self):
        from scripts.launcher import system_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        for statement, code in (("raise ModuleNotFoundError('private module detail', name='ensurepip')", 'system_python_ensurepip_missing'),
                                ("raise ImportError('private DLL detail')", 'system_python_module_failed')):
            wrapper = ('import builtins\noriginal_import = builtins.__import__\n'
                       'def controlled_import(name, *args, **kwargs):\n'
                       '    if name == "ensurepip":\n        ' + statement + '\n'
                       '    return original_import(name, *args, **kwargs)\n'
                       'builtins.__import__ = controlled_import\n')
            result = subprocess.run([str(python), '-I', '-S', '-c', wrapper + system_python._PROBE],
                                    capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('private', result.stdout)
            with self.subTest(code=code), patch.object(system_python, 'controlled_run', return_value=result):
                with self.assertRaises(system_python.SystemPythonError) as caught:
                    system_python.discover_python(str(python))
            self.assertEqual(caught.exception.code, code)

    def test_process_failure_and_timeout_are_not_misreported_as_missing_python(self):
        from scripts.launcher import system_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        with patch.object(system_python, 'controlled_run', return_value=subprocess.CompletedProcess([], -1073741515, '', 'private path/credential')):
            with self.assertRaises(system_python.SystemPythonError) as caught:
                system_python.discover_python(str(python))
        self.assertEqual(caught.exception.code, 'system_python_process_failed')
        self.assertIn('-1073741515', str(caught.exception))
        self.assertNotIn('private', str(caught.exception))
        with patch.object(system_python, 'controlled_run', side_effect=subprocess.TimeoutExpired('private command', 5)):
            with self.assertRaises(system_python.SystemPythonError) as caught:
                system_python.discover_python(str(python))
        self.assertEqual(caught.exception.code, 'system_python_timeout')
        self.assertNotIn('private', str(caught.exception))

    def test_stale_discovery_paths_do_not_hide_missing_component(self):
        from scripts.launcher import system_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        value = {'version': [3, 11], 'bits': 64, 'implementation': 'cpython',
                 'base': str(python), 'modules': {'sysconfig': 'ok', 'venv': 'ok', 'ensurepip': 'missing'}}
        with patch.object(system_python, '_candidates', return_value=[[str(python)], ['/missing/python']]), \
             patch.object(system_python, 'controlled_run', side_effect=[subprocess.CompletedProcess([], 0, json.dumps(value), ''), FileNotFoundError()]):
            with self.assertRaises(system_python.SystemPythonError) as caught:
                system_python.discover_python()
        self.assertEqual(caught.exception.code, 'system_python_ensurepip_missing')

    def test_other_python_versions_do_not_hide_process_start_failure(self):
        from scripts.launcher import system_python
        failure = PermissionError(13, 'private path')
        value = {'version': [3, 12], 'bits': 64, 'implementation': 'cpython'}
        with patch.object(system_python, '_candidates', return_value=[['first'], ['second'], ['stale']]), \
             patch.object(system_python, 'controlled_run', side_effect=[failure, subprocess.CompletedProcess([], 0, json.dumps(value), ''), FileNotFoundError()]):
            with self.assertRaises(system_python.SystemPythonError) as caught:
                system_python.discover_python()
        self.assertEqual(caught.exception.code, 'system_python_start_failed')
        self.assertIn('13', str(caught.exception))
        self.assertNotIn('private', str(caught.exception))

    def test_manual_python_command_and_quoted_path_select_valid_interpreter(self):
        from scripts.launcher.system_python import discover_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        with patch('scripts.launcher.system_python.shutil.which', return_value=str(python)):
            self.assertEqual(discover_python('python'), python)
        self.assertEqual(discover_python(f'"{python}"'), python)
        self.assertEqual(discover_python(str(python.parent)), python)

    def test_invalid_manual_selection_does_not_silently_fall_back(self):
        from scripts.launcher.system_python import discover_python
        with self.assertRaises(LauncherError):
            discover_python('/missing/python.exe')

    def test_path_search_continues_past_store_alias_and_incompatible_python(self):
        from scripts.launcher.system_python import discover_python
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            alias = root / 'Microsoft/WindowsApps'
            wrong = root / 'wrong'
            for directory in (alias, wrong):
                directory.mkdir(parents=True)
                for name in ('python3.11', 'python', 'python3'):
                    executable = directory / (name + ('.exe' if os.name == 'nt' else ''))
                    executable.write_text('invalid fixture')
                    executable.chmod(0o700)
            search = os.pathsep.join(map(str, (alias, wrong, python.parent)))
            real_which = __import__('shutil').which
            def which(name, **kwargs):
                return None if Path(name).stem == 'py' else real_which(name, **kwargs)
            with patch.dict(os.environ, {'PATH': search}), patch.object(sys, 'frozen', True, create=True), \
                 patch('scripts.launcher.system_python.shutil.which', side_effect=which):
                self.assertEqual(discover_python(), python)

    def test_manager_passes_explicit_choice_through_normalization_to_selection(self):
        from scripts.manager.operations import _python_choice
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        values = normalize_values('bundle', {'python_command': str(python), 'output': '/bundle'})
        args = arguments({'action': 'bundle', **values})
        with patch('scripts.launcher.system_python._candidates', return_value=[]):
            self.assertEqual(_python_choice(args), {'python_executable': python})

    def test_windows_registry_search_uses_executable_path_and_both_views(self):
        from scripts.launcher.system_python import _windows_candidates
        executable = '/custom/Python311/python.exe'
        def open_key(hive, path, reserved, access):
            if hive != 'user' or access != 3 or '\\3.11\\' not in path:
                raise FileNotFoundError
            return nullcontext('registered')
        def query(key, name):
            if key == 'registered' and name == 'ExecutablePath':
                return executable, 1
            raise FileNotFoundError
        registry = SimpleNamespace(HKEY_CURRENT_USER='user', HKEY_LOCAL_MACHINE='machine',
            KEY_READ=1, KEY_WOW64_64KEY=4, KEY_WOW64_32KEY=2, OpenKey=open_key, QueryValueEx=query)
        with patch.dict(sys.modules, {'winreg': registry}):
            self.assertIn([executable], list(_windows_candidates()))

    def test_windows_path_accepts_versioned_executable_name(self):
        from scripts.launcher.system_python import _path_candidates
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root / 'python3.11.exe'
            executable.write_text('fixture')
            executable.chmod(0o700)
            windows = SimpleNamespace(name='nt', get_exec_path=lambda: [str(root)])
            with patch('scripts.launcher.system_python.os', windows):
                self.assertEqual(list(_path_candidates('python3.11')), [[str(executable)]])

    def test_windows_default_install_directory_is_a_discovery_hint(self):
        from scripts.launcher.system_python import _windows_candidates
        def missing_key(*_):
            raise FileNotFoundError
        registry = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2,
            KEY_READ=1, KEY_WOW64_64KEY=4, KEY_WOW64_32KEY=2,
            OpenKey=missing_key)
        with patch.dict(sys.modules, {'winreg': registry}), patch.dict(os.environ, {'LOCALAPPDATA': '/operator/local'}):
            self.assertIn([str(Path('/operator/local/Programs/Python/Python311/python.exe'))], list(_windows_candidates()))

    def test_provision_and_later_start_keep_system_selection_without_managed_python(self):
        from scripts.launcher import installation
        from scripts.launcher.installation_profiles import provision_profile, load_profile
        from scripts.launcher_test_support import create_project
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
            self.assertEqual(dependencies.call_args.kwargs['cache_root'], home / 'cache' / 'packages')
            self.assertEqual(load_profile(project, 'dev', home)['python_executable'], str(python))
            inspect = mocks.enter_context(patch.object(toolchain, 'inspect_toolchain', return_value=[{'status': 'ready'}]))
            tools = mocks.enter_context(patch.object(toolchain, '_environment', return_value={'AWCENTER_MANAGED_PYTHON': str(python)}))
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
                 'platform': 'win-arm64', 'base': str(Path(sys.executable).resolve()),
                 'modules': {'sysconfig': 'ok', 'venv': 'ok', 'ensurepip': 'ok'}}
        failures = []
        with patch.object(sys, 'platform', 'win32'), \
             patch('scripts.launcher.system_python.controlled_run', return_value=subprocess.CompletedProcess([], 0, json.dumps(value), '')):
            self.assertIsNone(_probe(['python'], failures=failures))
        self.assertEqual(failures[-1].code, 'system_python_architecture')

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

    def test_bundle_does_not_borrow_prepared_system_toolchain(self):
        from scripts.manager.operations import _bundle
        from scripts.launcher_test_support import create_project
        args = arguments({'action': 'bundle', 'output': '/bundle', 'manager_distribution': '/manager'})
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary).resolve())
            args.progress = lambda _: None
            with patch('scripts.launcher.system_python.discover_python') as discover, \
                 patch.object(toolchain, 'toolchain_environment') as env, \
                 patch('scripts.manager.distribution.prepare_full_manager') as prepare:
                _bundle(project, args, lambda _: None)
            discover.assert_not_called()
            env.assert_not_called()
            prepare.assert_called_once()

    def test_runtime_selection_is_profile_scoped_and_preserves_keys(self):
        from scripts.launcher.installation_profiles import provision_profile, load_profile, update_python_runtime
        from scripts.launcher_test_support import create_project
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
        from scripts.launcher_test_support import create_project
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary).resolve())
            project.python.parent.mkdir(parents=True)
            project.python.write_text('fixture')
            answers = [subprocess.CompletedProcess([], 0, 'True\n', ''),
                       subprocess.CompletedProcess([], 0, json.dumps(str(project.root / 'other-python')) + '\n', '')]
            with patch('scripts.launcher.installation_dependencies.capture', side_effect=answers):
                with self.assertRaisesRegex(LauncherError, '.venv'):
                    _ensure_venv(project, {}, expected_python=Path(sys.executable).resolve())

    def test_manager_default_is_system_python_and_checkbox_is_boolean(self):
        self.assertIs(normalize_values('provision', {}).get('install_python'), False)
        self.assertIs(normalize_values('provision', {'install_python': True})['install_python'], True)
        self.assertIs(arguments({'action': 'provision'}).install_python, False)

    def test_system_mode_installs_only_node_and_npm(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve() / 'private'
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


class WindowsConsolePythonTests(unittest.TestCase):
    def setUp(self):
        from scripts.launcher import system_python
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / 'Python İstanbul'
        self.root.mkdir()
        self.windowed = self.root / 'pythonw.exe'
        self.console = self.root / 'python.exe'
        self.windowed.write_bytes(b'windowed fixture')
        self.console.write_bytes(b'console fixture')
        self.version = [3, 11]
        self.probed = []
        self.enterContext(patch.object(sys, 'platform', 'win32'))
        self.enterContext(patch.object(system_python, 'controlled_run', side_effect=self.probe))

    def probe(self, command, **options):
        executable = Path(command[0])
        self.probed.append(executable)
        if not executable.is_file():
            raise FileNotFoundError()
        value = {'version': self.version if executable == self.console else [3, 11],
                 'micro': 9, 'bits': 64, 'implementation': 'cpython',
                 'platform': 'win-amd64', 'base': str(executable),
                 'modules': {'sysconfig': 'ok', 'venv': 'ok', 'ensurepip': 'ok'}}
        return subprocess.CompletedProcess(command, 0, json.dumps(value), '')

    def test_explicit_windowed_python_uses_validated_console_sibling(self):
        from scripts.launcher.system_python import discover_python, validate_python
        self.assertEqual(discover_python(str(self.windowed)), self.console)
        self.assertEqual(validate_python(self.windowed), self.console)
        self.assertEqual(self.probed, [self.console, self.console])

    def test_automatic_windowed_manager_selection_returns_console_python(self):
        from scripts.launcher.system_python import discover_python
        with patch.object(sys, '_base_executable', str(self.windowed)), \
             patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(discover_python(), self.console)

    def test_windowed_python_does_not_hide_incompatible_console_sibling(self):
        from scripts.launcher.system_python import SystemPythonError, discover_python
        self.version = [3, 12]
        with self.assertRaises(SystemPythonError) as caught:
            discover_python(str(self.windowed))
        self.assertEqual(caught.exception.code, 'system_python_version')

    def test_missing_console_sibling_does_not_accept_windowed_interpreter(self):
        from scripts.launcher.system_python import SystemPythonError, validate_python
        self.console.unlink()
        with self.assertRaises(SystemPythonError) as caught:
            validate_python(self.windowed)
        self.assertEqual(caught.exception.code, 'system_python_path_missing')

    def test_non_windows_executable_name_is_not_rewritten(self):
        from scripts.launcher.system_python import validate_python
        with patch.object(sys, 'platform', 'linux'):
            self.assertEqual(validate_python(self.windowed), self.windowed)

    def test_saved_windowed_profile_environment_uses_console_python(self):
        home = self.root / 'private'
        with patch.object(toolchain, '_trusted_inventory', return_value={}), \
             patch.object(toolchain, '_inventory', return_value={}):
            for name, artifact in load_catalog().items():
                if name == 'python':
                    continue
                target = toolchain._directory(home, artifact)
                target.mkdir(parents=True)
                (target / toolchain.RECEIPT).write_text(json.dumps({
                    'name': name, 'version': artifact.version, 'sha256': artifact.sha256}))
            values = toolchain.toolchain_environment(home, python_executable=self.windowed)
        self.assertEqual(values['AWCENTER_MANAGED_PYTHON'], str(self.console))


if __name__ == '__main__':
    unittest.main()
