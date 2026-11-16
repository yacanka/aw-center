"""A ready Manager start shares its requested checks inside held leases."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from scripts.launcher import installation, installation_profiles as profiles, toolchain
from scripts.launcher.installation_sources import Artifact, SourceSettings
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project
from scripts.manager import ensure, operations


class ManagerRuntimeReuseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / 'home'
        source = self.root / 'source'
        source.mkdir()
        self.project = create_project(source)
        self.catalog = {}
        for name, version, executable in (
            ('python', '3.11.18', 'python/python.exe'),
            ('node', '22.23.4', 'node/node.exe'),
            ('npm', '10.9.4', 'package/bin/npm-cli.js'),
        ):
            archive = self.root / (name + '.zip')
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.writestr(executable, name)
            self.catalog[name] = Artifact(name, version, archive.name,
                'https://example.com/' + archive.name,
                hashlib.sha256(archive.read_bytes()).hexdigest(), 'zip', executable)
        for context in (
            patch.dict(os.environ, {}, clear=True),
            patch.object(profiles, 'installation_home', return_value=self.home),
            patch.object(toolchain, 'load_catalog', return_value=self.catalog),
            patch.object(operations, '_project_for', return_value=self.project),
            patch.object(installation, '_core_checks', return_value=[{'name': 'core', 'status': 'ready'}]),
        ):
            context.start()
            self.addCleanup(context.stop)
        profiles.provision_profile(self.project, 'dev', self.home)
        with patch.object(toolchain, 'fetch_artifact', side_effect=self.fetch), \
             patch.object(toolchain, '_check_version'):
            self.environment = toolchain.ensure_toolchain(self.home, SourceSettings())

    def fetch(self, artifact, cache, _settings):
        destination = cache / artifact.filename
        shutil.copyfile(self.root / artifact.filename, destination)
        return destination

    def execute(self, start, **request):
        events = []
        with patch.object(installation, 'start_profile', side_effect=start):
            operations.execute({'action': 'ensure', 'source_root': str(self.project.root), **request},
                               events.append, lambda: None, threading.Event())
        return events

    def start(self, project, name, *, on_ready, on_health, validation_policy='managed'):
        profile = profiles.load_profile(project, name)
        environment = toolchain.toolchain_environment(Path(profile['installation_home']),
                                                      **installation._runtime_options(profile),
                                                      verify=validation_policy != 'developer')
        self.assertEqual(environment, self.environment)
        on_ready(profile)

    def tamper(self, name, home=None):
        artifact = self.catalog[name]
        target = (home or self.home) / 'runtimes' / (name + '-' + artifact.version)
        (target / artifact.executable).write_bytes(b'modified runtime')

    def test_ready_start_inventories_installed_bytes_once_per_runtime(self):
        with patch.object(toolchain, '_inventory', wraps=toolchain._inventory) as inventory:
            events = self.execute(self.start)
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(inventory.call_count, 3)

    def test_ready_start_probes_selected_python_once(self):
        python = self.root / 'system/python.exe'
        python.parent.mkdir()
        python.write_bytes(b'operator-selected interpreter')
        profile = profiles.load_profile(self.project, 'dev')
        profiles.update_python_runtime(self.project, profile, python)
        # Keep environment construction real; only the native executable probe
        # is replaced because these fixture bytes are not executable runtimes.
        with patch('scripts.launcher.system_python.validate_python', return_value=python) as probe:
            self.environment = toolchain.toolchain_environment(self.home, python_executable=python)
            probe.reset_mock()
            events = self.execute(self.start)
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(probe.call_count, 1)

    def test_ready_start_probes_legacy_windowed_python_once_and_uses_console_base(self):
        python = self.root / 'system/python.exe'
        python.parent.mkdir()
        python.write_bytes(b'operator-selected console interpreter')
        windowed = python.with_name('pythonw.exe')
        windowed.write_bytes(b'legacy windowed interpreter')
        profile = profiles.load_profile(self.project, 'dev')
        profiles.update_python_runtime(self.project, profile, windowed)

        def start(project, name, *, on_ready, validation_policy='managed', **_):
            profile = profiles.load_profile(project, name)
            self.assertEqual(profile['python_executable'], str(windowed))
            environment = toolchain.toolchain_environment(self.home, **installation._runtime_options(profile),
                                                          verify=validation_policy != 'developer')
            self.assertEqual(environment['AWCENTER_MANAGED_PYTHON'], str(python))
            on_ready(profile)

        for policy in ('managed', 'developer'):
            with self.subTest(policy=policy), \
                 patch('scripts.launcher.system_python.validate_python', return_value=python) as probe, \
                 patch.object(toolchain, 'controlled_run', side_effect=self.version_result):
                events = self.execute(start, source_selection='explicit', validation_policy=policy)
                self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
                self.assertEqual(probe.call_count, 1)
                self.assertEqual(profiles.load_profile(self.project, 'dev')['python_executable'], str(windowed))

    def version_result(self, command, **_):
        name = 'npm' if len(command) == 3 else 'python' if Path(command[0]).name == 'python.exe' else 'node'
        version = self.catalog[name].version
        stdout = 'Python ' + version if name == 'python' else version
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')

    def test_developer_ready_start_probes_each_runtime_once_per_operation(self):
        with patch.object(toolchain, 'controlled_run', side_effect=self.version_result) as version, \
             patch.object(toolchain, '_inventory', wraps=toolchain._inventory) as inventory:
            for _ in range(2):
                events = self.execute(self.start, source_selection='explicit', validation_policy='developer')
                self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
            self.assertEqual(version.call_count, 6)
            self.assertEqual(inventory.call_count, 0)

    def test_selected_system_npm_is_probed_once_during_ready_start(self):
        from scripts.launcher import system_node
        node = self.root / 'system/node.exe'
        node.parent.mkdir()
        node.write_bytes(b'operator-selected node')
        npm = node.parent / 'node_modules/npm/bin/npm-cli.js'
        npm.parent.mkdir(parents=True)
        npm.write_bytes(b'operator-selected npm')
        profile = profiles.load_profile(self.project, 'dev')
        profiles.update_node_runtime(self.project, profile, node)

        def probe(command, **_):
            stdout = (json.dumps({'execPath': str(node), 'version': 'v22.23.4', 'arch': 'x64',
                                  'platform': 'win32'}) if '--eval' in command else '10.9.4')
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')

        def start(project, name, *, on_ready, validation_policy='managed', **_):
            profile = profiles.load_profile(project, name)
            environment = toolchain.toolchain_environment(self.home, **installation._runtime_options(profile),
                                                          verify=validation_policy != 'developer')
            self.assertEqual(environment['AWCENTER_MANAGED_NODE'], str(node))
            self.assertEqual(environment['AWCENTER_MANAGED_NPM_CLI'], str(npm))
            on_ready(profile)

        for policy in ('managed', 'developer'):
            with self.subTest(policy=policy), \
                 patch.object(system_node, 'controlled_run', side_effect=probe) as native, \
                 patch.object(toolchain, 'controlled_run', side_effect=self.version_result):
                events = self.execute(start, source_selection='explicit', validation_policy=policy)
                self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
                self.assertEqual(native.call_count, 2)

    def test_developer_failed_or_cancelled_start_does_not_retain_version_checks(self):
        for error in (LauncherError, toolchain.OperationCancelled):
            with self.subTest(error=error.__name__), \
                 patch.object(toolchain, 'controlled_run', side_effect=self.version_result) as version:
                def fail(*_, **__):
                    toolchain.toolchain_environment(self.home, verify=False)
                    raise error('startup interrupted')
                events = self.execute(fail, source_selection='explicit', validation_policy='developer')
                expected = ({'type': 'done', 'ok': True, 'cancelled': True} if error is toolchain.OperationCancelled else
                            {'type': 'done', 'ok': False})
                self.assertEqual(events[-1], expected, events)
                self.assertEqual(version.call_count, 3)
                self.assertTrue(all(row['status'] == 'ready' for row in
                                    toolchain.inspect_toolchain(self.home, verify=False)))
                self.assertEqual(version.call_count, 6)

    def test_scoped_checks_are_copied_for_both_caller_and_consumer(self):
        with patch.object(toolchain, 'controlled_run', side_effect=self.version_result) as version:
            checks = toolchain.inspect_toolchain(self.home, verify=False)
            with toolchain.verified_toolchain_scope(self.home, checks, verify=False):
                checks[0]['status'] = 'invalid'
                first = toolchain.inspect_toolchain(self.home, verify=False)
                self.assertEqual(first[0]['status'], 'ready')
                first[0]['status'] = 'invalid'
                self.assertEqual(toolchain.toolchain_environment(self.home, verify=False), self.environment)
            self.assertEqual(version.call_count, 3)

    def test_explicit_inspection_after_start_rechecks_modified_bytes(self):
        events = self.execute(self.start)
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.tamper('node')
        checks = toolchain.inspect_toolchain(self.home)
        self.assertEqual(next(row['status'] for row in checks if row['name'] == 'node'), 'invalid')

    def test_developer_inspection_cannot_replace_full_runtime_verification(self):
        args = operations.arguments({'action': 'ensure', 'source_root': str(self.project.root),
                                     'source_selection': 'explicit', 'validation_policy': 'developer'})
        args.progress = lambda _: None

        def start(*_, **__):
            self.tamper('node')
            checks = toolchain.inspect_toolchain(self.home)
            self.assertEqual(next(row['status'] for row in checks if row['name'] == 'node'), 'invalid')

        with patch.object(toolchain, '_check_version'), \
             patch.object(operations, '_run_lifecycle', side_effect=start):
            ensure.claimed(self.project, 'start', args, lambda _: None)

    def test_start_does_not_reuse_verification_for_other_home_or_options(self):
        other = self.root / 'other-home'
        shutil.copytree(self.home, other)
        self.tamper('node', other)
        invalid_python = self.root / 'unusable-python.exe'
        invalid_python.write_bytes(b'invalid interpreter')
        def start(project, name, *, on_ready, on_health):
            checks = toolchain.inspect_toolchain(other)
            self.assertEqual(next(row['status'] for row in checks if row['name'] == 'node'), 'invalid')
            with patch('scripts.launcher.system_python.validate_python', side_effect=LauncherError('invalid')):
                checks = toolchain.inspect_toolchain(self.home, python_executable=invalid_python)
            self.assertEqual(checks[0]['status'], 'invalid')
            self.start(project, name, on_ready=on_ready, on_health=on_health)
        events = self.execute(start)
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)

    def test_start_failure_does_not_leave_verification_in_context(self):
        def fail(project, name, *, on_ready, on_health):
            toolchain.toolchain_environment(self.home)
            raise LauncherError('startup interrupted')
        events = self.execute(fail)
        self.assertEqual(events[-1], {'type': 'done', 'ok': False}, events)
        self.tamper('python')
        self.assertEqual(toolchain.inspect_toolchain(self.home)[0]['status'], 'invalid')

    def test_provision_does_not_reuse_preparation_time_verification(self):
        def provision(project, args):
            self.tamper('node')
            return []
        with patch.object(installation, '_core_checks', return_value=[{'name': 'core', 'status': 'missing'}]), \
             patch.object(installation, 'provision', side_effect=provision):
            events = self.execute(self.start)
        self.assertEqual(events[-1], {'type': 'done', 'ok': False}, events)
        self.assertFalse(any(event['type'] == 'ready' for event in events))


if __name__ == '__main__':
    unittest.main()
