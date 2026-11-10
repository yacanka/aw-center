"""Completed acquisitions survive retries without weakening source or integrity checks."""
import json
from contextlib import nullcontext
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

from scripts.launcher import installation_dependencies as deps
from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher.model import LauncherError
from scripts.launcher.process import OperationCancelled, operation_control
from scripts.launcher_test_support import create_project


_NPM_CONTENT = '_cacache/content-v2/sha512/aa/bb/' + 'a' * 124


class PersistentPackageAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = create_project(self.root)
        (self.project.frontend / 'package-lock.json').write_text('{}')
        self.cache = self.root / 'private-cache'
        self.downloads = []
        self.installs = []
        self.fail_install = False
        self.cancel_download = None
        self.target = ['cpython', '3.11.15', 'win-amd64']
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(deps, 'capture', side_effect=self.package_command).start()
        mock.patch.object(deps, '_npm_command', return_value=['node', 'npm-cli.js']).start()
        self.tool_env = {'AWCENTER_MANAGED_NODE': 'node'}

    def package_command(self, command, *_, **kwargs):
        if '-c' in command or '-p' in command:
            return subprocess.CompletedProcess(command, 0, json.dumps(self.target), '')
        if 'wheel' in command:
            candidate = Path(command[command.index('--wheel-dir') + 1])
            candidate.mkdir(exist_ok=True)
            (candidate / 'fixture-1.0-py3-none-any.whl').write_bytes(b'wheel fixture')
            self.downloads.append(command[command.index('--index-url') + 1])
            if self.cancel_download:
                self.cancel_download.set()
        elif '--registry' in command:
            candidate = Path(command[command.index('--cache') + 1])
            content = candidate / _NPM_CONTENT
            content.parent.mkdir(parents=True)
            content.write_bytes(b'npm fixture')
            logs = candidate / '_logs/debug.log'
            logs.parent.mkdir()
            logs.write_text('sensitive package diagnostic')
            self.downloads.append(command[command.index('--registry') + 1])
            if self.cancel_download:
                self.cancel_download.set()
        elif 'install' in command or '--offline' in command:
            flag = '--find-links' if 'install' in command else '--cache'
            directory = Path(command[command.index(flag) + 1])
            filename = 'fixture-1.0-py3-none-any.whl' if flag == '--find-links' else _NPM_CONTENT
            self.installs.append((directory, (directory / filename).read_bytes()))
            if '--offline' in command:
                (directory / _NPM_CONTENT).write_bytes(b'install mutation')
            if self.fail_install:
                return subprocess.CompletedProcess(command, 1, '', '[WinError 5] private path')
        return subprocess.CompletedProcess(command, 0, '', '')

    def install(self, kind='python', settings=None, project=None):
        with tempfile.TemporaryDirectory(dir=self.root) as stage:
            operation = deps._python_packages if kind == 'python' else deps._frontend_packages
            operation(project or self.project, settings or SourceSettings(), self.tool_env,
                      Path(stage), cache_root=self.cache)

    def test_failed_install_retry_reuses_verified_acquisition_for_both_package_tools(self):
        for kind in ('python', 'npm'):
            with self.subTest(kind=kind):
                before = len(self.downloads)
                self.fail_install = True
                with self.assertRaises(deps.PackageCommandError):
                    self.install(kind)
                self.fail_install = False
                self.install(kind)
                self.assertEqual(len(self.downloads), before + 1)
                self.assertEqual(self.installs[-1][1], b'wheel fixture' if kind == 'python' else b'npm fixture')
        self.assertFalse(list(self.cache.rglob('debug.log')))

    def test_development_and_production_keep_separate_environments_and_share_acquisition(self):
        self.install()
        other = self.root / 'production'
        other.mkdir()
        project = create_project(other)
        self.install(project=project)
        self.assertEqual(self.downloads, ['https://pypi.org/simple'])
        self.assertEqual(self.installs[0][0], self.installs[1][0])
        self.assertNotEqual(project.venv, self.project.venv)

    def test_changed_lock_or_runtime_target_requires_new_acquisition(self):
        self.install()
        self.project.requirements.write_text('Django==5.2.1\n')
        self.install()
        self.target = ['cpython', '3.11.16', 'win-amd64']
        self.install()
        self.assertEqual(len(self.downloads), 3)

    def test_changed_frontend_manifest_requires_new_acquisition(self):
        self.install('npm')
        self.project.package_json.write_text('{"dependencies": {}}')
        self.install('npm')
        self.assertEqual(len(self.downloads), 2)

    def test_corrupt_completed_acquisition_fails_without_redownload_or_install(self):
        self.install()
        next(self.cache.rglob('*.whl')).write_bytes(b'tampered')
        with self.assertRaisesRegex(LauncherError, 'doğrulanamadı'):
            self.install()
        self.assertEqual(len(self.downloads), 1)
        self.assertEqual(len(self.installs), 1)

    def test_source_modes_and_selected_indexes_cannot_reuse_other_origins(self):
        self.install()
        self.install(settings=SourceSettings(mode='corporate', python_index_url='https://one.invalid/simple'))
        self.install(settings=SourceSettings(mode='corporate', python_index_url='https://two.invalid/simple'))
        self.install(settings=SourceSettings(mode='restricted', python_index_url='https://one.invalid/simple'))
        with self.assertRaises(LauncherError):
            self.install(settings=SourceSettings(mode='offline'))
        self.assertEqual(self.downloads, ['https://pypi.org/simple', 'https://one.invalid/simple',
                                         'https://two.invalid/simple', 'https://one.invalid/simple'])
        for manifest in self.cache.rglob('manifest.json'):
            self.assertNotIn('https://', manifest.read_text())

    def test_verified_offline_bundle_has_precedence_over_warm_network_cache(self):
        self.install()
        offline = self.root / 'offline'
        (offline / 'wheels').mkdir(parents=True)
        (offline / 'wheels/fixture-1.0-py3-none-any.whl').write_bytes(b'offline fixture')
        with mock.patch.object(deps, '_offline_dependencies', return_value=offline):
            self.install(settings=SourceSettings(offline_dir=offline))
        self.assertEqual(len(self.downloads), 1)
        self.assertEqual(self.installs[-1][1], b'offline fixture')

    def test_cancellation_after_acquisition_cannot_publish_or_install_partial_cache(self):
        for kind in ('python', 'npm'):
            with self.subTest(kind=kind):
                event = threading.Event()
                self.cancel_download = event
                with operation_control(event), self.assertRaises(OperationCancelled):
                    self.install(kind)
                self.assertFalse(list(self.cache.rglob('manifest.json')))
                self.assertFalse(self.installs)
                self.cancel_download = None
        self.install()
        self.assertEqual(len(self.downloads), 3)

    def test_successful_stage_restart_does_not_acquire_or_reinstall(self):
        target = self.project.venv
        target.mkdir()
        def install():
            self.install()
            (target / 'installed').write_bytes(b'installed fixture')
        self.assertTrue(deps.dependency_stage(target, self.project.requirements, install))
        self.assertFalse(deps.dependency_stage(target, self.project.requirements, install))
        self.assertEqual(len(self.downloads), 1)
        self.assertEqual(len(self.installs), 1)

    def test_deleted_added_or_invalid_cache_metadata_is_fatal(self):
        for mutation in ('missing', 'added', 'identity', 'symlink'):
            with self.subTest(mutation=mutation):
                self.cache = self.root / ('cache-' + mutation)
                self.install()
                manifest = next(self.cache.rglob('manifest.json'))
                if mutation == 'missing':
                    manifest.unlink()
                elif mutation == 'added':
                    (manifest.parent / 'data/unexpected.whl').write_bytes(b'unexpected')
                elif mutation == 'identity':
                    saved = json.loads(manifest.read_text())
                    saved['identity'] = '0' * 64
                    manifest.write_text(json.dumps(saved))
                else:
                    (manifest.parent / 'data/external').symlink_to(self.root, target_is_directory=True)
                before = (len(self.downloads), len(self.installs))
                with self.assertRaises(LauncherError):
                    self.install()
                self.assertEqual((len(self.downloads), len(self.installs)), before)

    def test_cancellation_while_verifying_warm_cache_is_not_replaced_by_integrity_error(self):
        from scripts.launcher import package_cache
        self.install()
        digest = package_cache.file_sha256
        event = threading.Event()
        def cancel(path):
            value = digest(path)
            if path.suffix == '.whl':
                event.set()
            return value
        with operation_control(event), mock.patch.object(package_cache, 'file_sha256', side_effect=cancel):
            with self.assertRaises(OperationCancelled):
                self.install()
        self.assertEqual(len(self.installs), 1)

    def test_unsuccessful_acquisition_is_never_published(self):
        command = self.package_command
        def fail(command_args, *args, **kwargs):
            result = command(command_args, *args, **kwargs)
            if 'wheel' in command_args or '--registry' in command_args:
                return subprocess.CompletedProcess(command_args, 1, '', 'HTTP error 503')
            return result
        with mock.patch.object(deps, 'capture', side_effect=fail):
            for kind in ('python', 'npm'):
                with self.subTest(kind=kind), self.assertRaises(LauncherError):
                    self.install(kind)
        self.assertFalse(list(self.cache.rglob('manifest.json')))
        self.assertFalse(self.installs)
        self.install()
        self.assertEqual(len(self.downloads), 3)

    def test_install_dependencies_wires_shared_cache_and_retains_successful_receipts(self):
        self.project.venv.mkdir()
        modules = self.project.frontend / 'node_modules'
        modules.mkdir()
        events = []
        settings = SourceSettings(progress=events.append)
        self.fail_install = True
        with mock.patch.object(deps, '_ensure_venv'), \
             mock.patch.object(deps, 'package_trust_environment', side_effect=lambda env, **_: nullcontext(env)):
            with self.assertRaises(deps.PackageCommandError):
                deps.install_dependencies(self.project, settings, self.tool_env, cache_root=self.cache)
            self.assertFalse((self.project.venv / '.awcenter-packages.json').exists())
            self.fail_install = False
            deps.install_dependencies(self.project, settings, self.tool_env, cache_root=self.cache)
            deps.install_dependencies(self.project, settings, self.tool_env, cache_root=self.cache)
        self.assertEqual(self.downloads, ['https://pypi.org/simple', 'https://registry.npmjs.org'])
        self.assertEqual(len(self.installs), 3)
        self.assertTrue((self.project.venv / '.awcenter-packages.json').is_file())
        self.assertTrue((modules / '.awcenter-packages.json').is_file())
        self.assertTrue(any('kalıcı önbellek' in event for event in events))

    def test_windows_cache_and_install_paths_fit_legacy_limit_with_long_npm_digest(self):
        from scripts.launcher import package_cache
        windows_user = PureWindowsPath('C:/Users') / ('u' * 20) / 'AppData/Local'
        windows_cache = windows_user / 'AWCenter/cache/packages'
        paths = []
        copy = package_cache._copy_acquisition
        def observe(candidate, destination, kind):
            if kind == 'npm':
                paths.append(windows_cache / destination.relative_to(self.cache).as_posix() / _NPM_CONTENT)
            copy(candidate, destination, kind)
        self.project.venv.mkdir()
        (self.project.frontend / 'node_modules').mkdir()
        with mock.patch.object(deps, '_ensure_venv'), \
             mock.patch.object(deps, 'package_trust_environment', side_effect=lambda env, **_: nullcontext(env)), \
             mock.patch.object(package_cache, '_copy_acquisition', side_effect=observe):
            deps.install_dependencies(self.project, SourceSettings(), self.tool_env, cache_root=self.cache)
        manifest = next((self.cache / 'npm').rglob('manifest.json'))
        paths.append(windows_cache / manifest.parent.relative_to(self.cache).as_posix() / 'data' / _NPM_CONTENT)
        install = self.installs[-1][0].relative_to(Path(tempfile.gettempdir()).resolve())
        paths.append(windows_user / 'Temp' / install.as_posix() / _NPM_CONTENT)
        for path in paths:
            with self.subTest(length=len(str(path)), path=str(path)):
                self.assertLess(len(str(path)), 260)

    def test_verified_stages_skip_trust_setup_and_report_reuse(self):
        self.project.venv.mkdir()
        modules = self.project.frontend / 'node_modules'
        modules.mkdir()
        for target, lock in ((self.project.venv, self.project.requirements),
                             (modules, self.project.frontend / 'package-lock.json')):
            deps.dependency_stage(target, lock, lambda: (target / 'fixture').touch())
        events = []
        with mock.patch.object(deps, '_ensure_venv'), \
             mock.patch.object(deps, 'package_trust_environment',
                               side_effect=AssertionError('ready stages requested package TLS')), \
             mock.patch.object(deps.tempfile, 'TemporaryDirectory',
                               side_effect=AssertionError('ready stages requested temporary staging')):
            deps.install_dependencies(self.project, SourceSettings(progress=events.append), self.tool_env)
        self.assertFalse(any('hazırlanıyor' in event for event in events), events)
        self.assertEqual(sum('kullanılıyor' in event for event in events), 2, events)
        self.assertEqual(self.downloads, [])
        self.assertEqual(self.installs, [])

    def test_package_install_phase_is_visible_when_each_local_command_runs(self):
        events = []
        def observe(command, *args, **kwargs):
            if 'install' in command or '--offline' in command:
                self.assertIn('kuruluyor', events[-1], events)
                self.assertIn('Python' if 'install' in command else 'Frontend', events[-1])
            return self.package_command(command, *args, **kwargs)
        with mock.patch.object(deps, 'capture', side_effect=observe):
            for kind in ('python', 'npm'):
                self.install(kind, SourceSettings(progress=events.append))

    def test_changed_lock_cannot_hide_modified_existing_python_before_command(self):
        self.project.python.parent.mkdir(parents=True)
        deps.dependency_stage(self.project.venv, self.project.requirements,
                              lambda: self.project.python.write_bytes(b'original'))
        self.project.requirements.write_text('Django==5.3\n')
        self.project.python.write_bytes(b'changed')
        with mock.patch.object(deps, '_ensure_venv', side_effect=AssertionError('executed changed venv')), \
             self.assertRaises(LauncherError):
            deps.install_dependencies(self.project, SourceSettings(), self.tool_env)

    def test_interrupted_frontend_update_preserves_verified_tree_and_resumes(self):
        modules = self.project.frontend / 'node_modules'
        modules.mkdir()
        self.project.venv.mkdir()
        npm_lock = self.project.frontend / 'package-lock.json'
        deps.dependency_stage(self.project.venv, self.project.requirements,
                              lambda: (self.project.venv / 'fixture').touch())
        deps.dependency_stage(modules, npm_lock, lambda: (modules / 'module.js').write_bytes(b'previous'))
        npm_lock.write_text('{"changed": true}')
        def install(*_, **__):
            modules.mkdir(exist_ok=True)
            (modules / 'module.js').write_bytes(b'partial' if self.fail_install else b'complete')
            if self.fail_install:
                raise OperationCancelled()
        with mock.patch.object(deps, '_ensure_venv'), \
             mock.patch.object(deps, '_python_packages', side_effect=AssertionError('unrelated Python install')), \
             mock.patch.object(deps, '_frontend_packages', side_effect=install), \
             mock.patch.object(deps, 'package_trust_environment', side_effect=lambda env, **_: nullcontext(env)):
            self.fail_install = True
            with self.assertRaises(OperationCancelled):
                deps.install_dependencies(self.project, SourceSettings(), self.tool_env)
            self.fail_install = False
            deps.install_dependencies(self.project, SourceSettings(), self.tool_env)
        self.assertEqual((modules / 'module.js').read_bytes(), b'complete')
        backups = (self.project.root / '.runtime/npm-backups').glob('*/node_modules/module.js')
        self.assertEqual({path.read_bytes() for path in backups}, {b'previous', b'partial'})

    def test_changed_python_lock_restarts_partial_update_using_selected_interpreter(self):
        self.project.python.parent.mkdir(parents=True)
        deps.dependency_stage(self.project.venv, self.project.requirements,
                              lambda: self.project.python.write_bytes(b'previous'))
        self.project.requirements.write_text('Django==5.3\n')
        modules = self.project.frontend / 'node_modules'
        modules.mkdir()
        deps.dependency_stage(modules, self.project.frontend / 'package-lock.json',
                              lambda: (modules / 'module.js').touch())
        selected = self.root / 'selected-python.exe'
        selected.touch()
        def prepare_venv(*_, **__):
            self.assertFalse(self.project.python.exists(), 'old or partial interpreter was probed')
            self.project.python.parent.mkdir(parents=True)
            self.project.python.write_bytes(b'new interpreter')
        def install(*_, **__):
            (self.project.venv / 'library').write_bytes(b'partial' if self.fail_install else b'complete')
            if self.fail_install:
                raise OperationCancelled()
        with mock.patch.object(deps, '_ensure_venv', side_effect=prepare_venv), \
             mock.patch.object(deps, '_python_packages', side_effect=install), \
             mock.patch.object(deps, '_frontend_packages', side_effect=AssertionError('unrelated frontend install')), \
             mock.patch.object(deps, 'package_trust_environment', side_effect=lambda env, **_: nullcontext(env)):
            self.fail_install = True
            with self.assertRaises(OperationCancelled):
                deps.install_dependencies(self.project, SourceSettings(), self.tool_env,
                                          expected_python=selected, repair_venv=True)
            self.fail_install = False
            deps.install_dependencies(self.project, SourceSettings(), self.tool_env,
                                      expected_python=selected, repair_venv=True)
        self.assertEqual((self.project.venv / 'library').read_bytes(), b'complete')
        backups = self.project.root / '.runtime/venv-backups'
        self.assertIn(b'previous', {path.read_bytes() for path in backups.rglob(self.project.python.name)})
        self.assertEqual(next(backups.rglob('library')).read_bytes(), b'partial')

    def test_explicit_provision_updates_a_verified_old_python_lock(self):
        self.project.python.parent.mkdir(parents=True)
        deps.dependency_stage(self.project.venv, self.project.requirements,
                              lambda: self.project.python.write_bytes(b'old but verified'))
        self.project.requirements.write_text('Django==5.3\n')
        modules = self.project.frontend / 'node_modules'
        modules.mkdir()
        deps.dependency_stage(modules, self.project.frontend / 'package-lock.json',
                              lambda: (modules / 'module.js').touch())
        selected = self.root / 'selected-python.exe'
        selected.touch()
        def prepare(*args, **kwargs):
            self.project.python.parent.mkdir(exist_ok=True, parents=True)
            self.project.python.write_bytes(b'current')
        with mock.patch.object(deps, '_ensure_venv', side_effect=prepare), \
             mock.patch.object(deps, '_python_packages', side_effect=lambda *_, **__: (self.project.venv / 'updated').touch()), \
             mock.patch.object(deps, 'package_trust_environment', side_effect=lambda env, **_: nullcontext(env)):
            deps.install_dependencies(self.project, SourceSettings(), self.tool_env, expected_python=selected)
        self.assertTrue((self.project.venv / 'updated').is_file())

    def test_explicit_provision_preserves_legacy_venv_bound_to_selected_python(self):
        selected = self.root / 'python.exe'
        selected.touch()
        self.project.python.parent.mkdir(parents=True)
        self.project.python.write_bytes(b'unverified legacy runtime')
        (self.project.venv / 'pyvenv.cfg').write_text(f'executable = {selected}\n', encoding='utf-8')
        modules = self.project.frontend / 'node_modules'
        modules.mkdir()
        deps.dependency_stage(modules, self.project.frontend / 'package-lock.json', lambda: (modules / 'fixture').touch())
        def prepare(*_, **__):
            self.assertFalse(self.project.python.exists())
            self.project.python.parent.mkdir(parents=True)
            self.project.python.write_bytes(b'new')
        with mock.patch.object(deps, '_ensure_venv', side_effect=prepare), \
             mock.patch.object(deps, '_python_packages'), \
             mock.patch.object(deps, 'package_trust_environment', side_effect=lambda env, **_: nullcontext(env)):
            deps.install_dependencies(self.project, SourceSettings(), self.tool_env, expected_python=selected)
        backups = (self.project.root / '.runtime/venv-backups').rglob(self.project.python.name)
        self.assertEqual([path.read_bytes() for path in backups], [b'unverified legacy runtime'])

    def test_even_matching_interrupted_creation_marker_cannot_authorize_old_executable(self):
        selected = self.root / 'python.exe'
        selected.touch()
        self.project.python.parent.mkdir(parents=True)
        self.project.python.write_bytes(b'unverified partial runtime')
        (self.project.venv / '.awcenter-creating.json').write_text(json.dumps(
            {'version': 1, 'python': str(selected), 'source': str(self.project.root)}))
        def stop_before_creation(*_, **__):
            self.assertFalse(self.project.python.exists(), 'marker authorized an unchecked executable')
            raise OperationCancelled()
        with mock.patch.object(deps, '_ensure_venv', side_effect=stop_before_creation), \
             self.assertRaises(OperationCancelled):
            deps.install_dependencies(self.project, SourceSettings(), self.tool_env,
                                      expected_python=selected, repair_venv=True)

    def test_short_directory_collision_cannot_reuse_different_full_identity(self):
        from scripts.launcher import package_cache
        digest = package_cache.hashlib.sha256
        class Collision:
            def __init__(self, payload):
                self.value = digest(payload).hexdigest()
            def hexdigest(self):
                return 'a' * 12 + self.value[12:]
        with mock.patch.object(package_cache, 'hashlib', mock.Mock(sha256=Collision)):
            self.install()
            self.project.requirements.write_text('Django==5.2.1\n')
            with self.assertRaisesRegex(LauncherError, 'doğrulanamadı'):
                self.install()
        self.assertEqual(len(self.downloads), 1)

    def test_same_acquisition_is_locked_against_a_second_installer(self):
        from scripts.launcher.resource_locks import ResourceLockError
        entered, release = threading.Event(), threading.Event()
        failures = []
        command = self.package_command
        def slow(command_args, *args, **kwargs):
            if 'wheel' in command_args:
                entered.set()
                if not release.wait(5):
                    raise AssertionError('acquisition was not released')
            return command(command_args, *args, **kwargs)
        def install():
            try:
                self.install()
            except BaseException as error:
                failures.append(error)
        with mock.patch.object(deps, 'capture', side_effect=slow):
            worker = threading.Thread(target=install)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(ResourceLockError) as caught:
                    self.install()
                self.assertEqual(caught.exception.code, 'resource_busy')
            finally:
                release.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertFalse(failures)
        self.install()
        self.assertEqual(len(self.downloads), 1)

    def test_credential_or_query_bearing_sources_cannot_reuse_or_populate_cache(self):
        for kind, field in (('python', 'python_index_url'), ('npm', 'npm_registry_url')):
            self.install(kind)
            before = len(self.downloads), len(self.installs)
            for source in ('https://user:password@private.invalid/simple', 'https://private.invalid/simple?token=private'):
                with self.subTest(kind=kind, source=source), self.assertRaises(LauncherError):
                    self.install(kind, SourceSettings(mode='corporate', **{field: source}))
                self.assertEqual((len(self.downloads), len(self.installs)), before)
        for manifest in self.cache.rglob('manifest.json'):
            self.assertNotIn('private', manifest.read_text())

    def test_failed_pip_check_keeps_acquired_wheels_for_retry(self):
        command = self.package_command
        def fail_check(command_args, *args, **kwargs):
            if 'check' in command_args:
                return subprocess.CompletedProcess(command_args, 1, '', 'dependency mismatch')
            return command(command_args, *args, **kwargs)
        with mock.patch.object(deps, 'capture', side_effect=fail_check), self.assertRaises(deps.PackageCommandError):
            self.install()
        self.install()
        self.assertEqual(len(self.downloads), 1)
        self.assertEqual(len(self.installs), 2)

    def test_lock_change_during_acquisition_cannot_publish_under_previous_lock(self):
        command = self.package_command
        def change_lock(command_args, *args, **kwargs):
            result = command(command_args, *args, **kwargs)
            if 'wheel' in command_args:
                self.project.requirements.write_text('Django==5.2.1\n')
            return result
        with mock.patch.object(deps, 'capture', side_effect=change_lock), self.assertRaises(LauncherError):
            self.install()
        self.assertFalse(list(self.cache.rglob('manifest.json')))
        self.assertFalse(self.installs)


class SafePackageDiagnosticTests(unittest.TestCase):
    def test_reviewed_windows_failures_and_stage_are_preserved_without_raw_details(self):
        for diagnostic, code in (
            ('[WinError 206] hidden detail', 'package_path_too_long'),
            ('HINT: This error might have occurred since this system does not have Windows Long Path support enabled.', 'package_path_too_long'),
            ('[WinError 32] gizli dosya adı', 'package_file_in_use'),
            ('[WinError 5] gizli dosya adı', 'package_access_denied'),
            ('[WinError 112] gizli dosya adı', 'package_disk_full'),
        ):
            with self.subTest(diagnostic=diagnostic):
                result = subprocess.CompletedProcess([], 1, '', diagnostic)
                with self.assertRaises(deps.PackageCommandError) as caught:
                    deps._succeeded(result, 'Python paket kurulumu')
                self.assertEqual(caught.exception.code, code)
                self.assertIn('Python paket kurulumu', str(caught.exception))
                self.assertNotIn('hidden detail', str(caught.exception))
                self.assertNotIn('gizli dosya', str(caught.exception))
                self.assertFalse(deps.availability_failure(diagnostic + '\nE503', restricted=True))

    def test_unrecognized_numeric_windows_code_is_safe_and_does_not_enable_fallback(self):
        result = subprocess.CompletedProcess([], 1, '', '[WinError 1234] private detail')
        error = deps.PackageCommandError(result)
        self.assertIn('WinError: 1234', str(error))
        self.assertNotIn('private detail', str(error))
        self.assertFalse(deps.availability_failure(result.stderr + '\nE503', restricted=True))
