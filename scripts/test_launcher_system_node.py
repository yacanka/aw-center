"""Operator-installed Node selection and managed-tool acquisition boundaries."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from scripts.launcher import process, toolchain
from scripts.launcher.installation_sources import Artifact, SourceSettings
from scripts.launcher.model import LauncherError


HOST_NODE = shutil.which('node')


@unittest.skipUnless(HOST_NODE, 'A local Node executable is required for real probe tests')
class SystemNodeTests(unittest.TestCase):
    def setUp(self):
        self.node = Path(HOST_NODE).resolve()

    def probe(self, **changes):
        value = {'execPath': str(self.node), 'version': 'v22.13.0', 'arch': 'x64',
                 'platform': 'win32' if sys.platform == 'win32' else sys.platform}
        value.update(changes)
        return 'console.log(JSON.stringify(' + json.dumps(value) + '))'

    def test_real_node_probe_clears_inherited_hooks_and_returns_absolute_executable(self):
        from scripts.launcher.system_node import validate_node, SystemNodeError
        arch = subprocess.run([str(self.node), '--print', 'process.arch'], capture_output=True,
                              text=True, timeout=10, check=True).stdout.strip()
        with patch.dict(os.environ, {'NODE_OPTIONS': '--require ./private-injected-hook.js',
                                     'NODE_PATH': 'private-injected-directory'}):
            if arch == 'x64':
                self.assertEqual(validate_node(self.node), self.node)
            else:
                with self.assertRaises(SystemNodeError) as caught:
                    validate_node(self.node)
                self.assertEqual(caught.exception.code, 'system_node_architecture')

    def test_explicit_file_directory_quotes_and_relative_path_are_supported(self):
        from scripts.launcher import system_node
        for selection in (str(self.node), '"' + str(self.node) + '"', str(self.node.parent)):
            with self.subTest(selection=selection), patch.object(system_node, '_PROBE', self.probe()):
                self.assertEqual(system_node.discover_node(selection), self.node)
        # A relative path only exists on the current drive. CI's checkout and
        # installed Node commonly live on different Windows drives.
        previous = Path.cwd()
        try:
            os.chdir(self.node.parent)
            with patch.object(system_node, '_PROBE', self.probe()):
                self.assertEqual(system_node.discover_node('./' + self.node.name), self.node)
        finally:
            os.chdir(previous)

    def test_utf8_executable_path_is_not_decoded_with_windows_ansi(self):
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary).resolve() / 'İş araçları' / 'node.exe'
            executable.parent.mkdir()
            executable.write_bytes(b'operator executable fixture')
            value = {'execPath': str(executable), 'version': 'v22.13.0',
                     'arch': 'x64', 'platform': 'win32'}
            program = 'console.log(' + json.dumps(json.dumps(value, ensure_ascii=False)) + ')'
            def ansi_host_run(command, **options):
                options.setdefault('encoding', 'cp1254')
                return process.controlled_run([str(self.node), '--eval', program], **options)
            with patch.object(system_node, 'controlled_run', side_effect=ansi_host_run):
                self.assertEqual(system_node.validate_node(executable), executable)

    def test_supported_versions_and_architecture_are_checked_with_real_processes(self):
        from scripts.launcher import system_node
        for version in ('v22.13.0', 'v22.99.2', 'v24.0.0', 'v25.1.2'):
            with self.subTest(version=version), patch.object(system_node, '_PROBE', self.probe(version=version)):
                self.assertEqual(system_node.validate_node(self.node), self.node)
        for version in ('v20.19.0', 'v22.11.9', 'v22.12.0', 'v22.12.9', 'v23.9.0', 'v24.0.0-rc.1', 'v24.0.0+private'):
            with self.subTest(version=version), patch.object(system_node, '_PROBE', self.probe(version=version)):
                with self.assertRaises(system_node.SystemNodeError) as caught:
                    system_node.validate_node(self.node)
                self.assertEqual(caught.exception.code, 'system_node_version')
        for arch in ('ia32', 'arm64'):
            with self.subTest(arch=arch), patch.object(system_node, '_PROBE', self.probe(arch=arch)):
                with self.assertRaises(system_node.SystemNodeError) as caught:
                    system_node.validate_node(self.node)
                self.assertEqual(caught.exception.code, 'system_node_architecture')

    def test_windows_host_rejects_non_windows_node(self):
        from scripts.launcher import system_node
        with patch.object(sys, 'platform', 'win32'), patch.object(system_node, '_PROBE', self.probe(platform='linux')):
            with self.assertRaises(system_node.SystemNodeError) as caught:
                system_node.validate_node(self.node)
        self.assertEqual(caught.exception.code, 'system_node_platform')

    def test_explicit_invalid_selection_never_uses_automatic_candidates(self):
        from scripts.launcher import system_node
        with patch.object(system_node, '_candidates') as candidates:
            with self.assertRaises(system_node.SystemNodeError):
                system_node.discover_node('node --eval private-shell-expression')
        candidates.assert_not_called()

    def test_probe_timeout_and_failure_are_safe(self):
        from scripts.launcher import system_node
        for script, code in (('console.error("private detail"); process.exit(17)', 'process_failed'),
                             ('console.log("private invalid response")', 'invalid_response'),
                             ('setTimeout(() => {}, 10000)', 'timeout')):
            with self.subTest(code=code), patch.object(system_node, '_PROBE', script), \
                 patch.object(system_node, 'PROBE_TIMEOUT_SECONDS', 0.25):
                with self.assertRaises(system_node.SystemNodeError) as caught:
                    system_node.validate_node(self.node)
            self.assertEqual(caught.exception.code, 'system_node_' + code)
            self.assertNotIn('private', str(caught.exception))
            self.assertTrue(caught.exception.remedy)

    def test_running_probe_can_be_cancelled_without_discovery_fallback(self):
        from scripts.launcher import system_node
        stop = threading.Event()
        timer = threading.Timer(0.2, stop.set)
        timer.start()
        try:
            with process.operation_control(stop), patch.object(system_node, '_PROBE', 'setTimeout(() => {}, 30000)'):
                with self.assertRaises(process.OperationCancelled):
                    system_node.discover_node(str(self.node))
        finally:
            timer.cancel()

    def test_npm_cli_is_executed_by_selected_node_and_must_match_pin(self):
        from scripts.launcher.system_node import find_npm_cli
        with tempfile.TemporaryDirectory(prefix='node selection ') as temporary:
            root = Path(temporary).resolve()
            selected = root / self.node.name
            cli = root / 'node_modules/npm/bin/npm-cli.js'
            cli.parent.mkdir(parents=True)
            # The finder accepts a validated executable pointer and never calls npm.cmd.
            selected.write_text('selection fixture')
            cli.write_text('if(process.env.NODE_OPTIONS || process.env.NODE_PATH) process.exit(9); console.log("10.9.4")')
            from scripts.launcher import system_node
            original = system_node.controlled_run
            commands = []
            def run(command, **options):
                commands.append(command)
                return original([str(self.node), *command[1:]], **options)
            with patch.object(system_node, 'controlled_run', side_effect=run), \
                 patch.dict(os.environ, {'NODE_OPTIONS': '--require ./private-hook.js', 'NODE_PATH': 'private-hook'}):
                self.assertEqual(find_npm_cli(selected, '10.9.4'), cli)
                cli.write_text('console.log("10.9.3")')
                self.assertIsNone(find_npm_cli(selected, '10.9.4'))
            self.assertTrue(all(command[:2] == [str(selected), str(cli)] for command in commands))

    def test_npm_probe_cancellation_never_becomes_a_missing_npm_result(self):
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            cli = Path(temporary).resolve() / 'npm-cli.js'
            cli.write_text('setTimeout(() => {}, 30000)')
            stop = threading.Event()
            timer = threading.Timer(0.2, stop.set)
            timer.start()
            try:
                with process.operation_control(stop), patch.object(system_node, '_npm_candidates', return_value=[cli]):
                    with self.assertRaises(process.OperationCancelled):
                        system_node.find_npm_cli(self.node, '10.9.4')
            finally:
                timer.cancel()

    def test_compatible_npm_accepts_reviewed_versions_without_relaxing_exact_mode(self):
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            cli = Path(temporary).resolve() / 'npm-cli.js'
            with patch.object(system_node, '_npm_candidates', return_value=[cli]):
                for version in ('10.9.4', '10.9.5', '10.10.0', '11.0.0', '11.18.0'):
                    with self.subTest(version=version):
                        cli.write_text('console.log(' + json.dumps(version) + ')')
                        self.assertEqual(system_node.find_npm_cli(self.node, '10.9.4', compatible=True), cli)
                        expected = cli if version == '10.9.4' else None
                        self.assertEqual(system_node.find_npm_cli(self.node, '10.9.4'), expected)

    def test_compatible_npm_rejects_unsupported_and_nonstable_cli_versions(self):
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            cli = Path(temporary).resolve() / 'npm-cli.js'
            with patch.object(system_node, '_npm_candidates', return_value=[cli]):
                for version in ('9.9.9', '10.8.99', '10.9.3', '12.0.0', '11.18.0-rc.1',
                                '11.18.0+private', '11.018.0'):
                    with self.subTest(version=version):
                        cli.write_text('console.log(' + json.dumps(version) + ')')
                        self.assertIsNone(system_node.find_npm_cli(self.node, '10.9.4', compatible=True))

    def test_malformed_npm_version_requires_operator_action(self):
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            cli = Path(temporary).resolve() / 'npm-cli.js'
            with patch.object(system_node, '_npm_candidates', return_value=[cli]):
                for version in ('v11.18.0', '/private/npm'):
                    with self.subTest(version=version):
                        cli.write_text('console.log(' + json.dumps(version) + ')')
                        with self.assertRaises(system_node.SystemNodeError) as caught:
                            system_node.find_npm_cli(self.node, '10.9.4', compatible=True)
                        self.assertEqual(caught.exception.reason, 'invalid_response')


class SystemNodeDiscoveryTests(unittest.TestCase):
    def test_path_discovery_continues_past_an_incompatible_installation(self):
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            bad, good = root / 'bad', root / 'good'
            bad.mkdir()
            good.mkdir()
            filename = 'node.exe' if sys.platform == 'win32' else 'node'
            for directory in (bad, good):
                (directory / filename).write_text('fixture')
                (directory / filename).chmod(0o700)
            def validate(candidate):
                if candidate.parent == bad:
                    raise system_node.SystemNodeError('version')
                return candidate
            with patch.dict(os.environ, {'PATH': os.pathsep.join((str(bad), str(good)))}), \
                 patch.object(system_node, 'validate_node', side_effect=validate):
                self.assertEqual(system_node.discover_node(), good / filename)

    def test_managed_runtime_is_excluded_without_executing_it(self):
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            node = root / 'AWCenter/runtimes/node-22/node.exe'
            node.parent.mkdir(parents=True)
            node.write_text('fixture')
            with patch.dict(os.environ, {'LOCALAPPDATA': str(root)}), \
                 patch.object(system_node, 'controlled_run') as run:
                with self.assertRaises(system_node.SystemNodeError) as caught:
                    system_node.discover_node(str(node))
            self.assertEqual(caught.exception.code, 'system_node_excluded')
            run.assert_not_called()

    def test_discovery_deduplicates_aliases_before_repeating_failed_probe(self):
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            node = Path(temporary).resolve() / 'node.exe'
            node.write_text('fixture')
            alternate = node.parent / '.' / node.name
            with patch.object(system_node, '_candidates', return_value=[node, alternate]), \
                 patch.object(system_node, 'controlled_run', side_effect=subprocess.TimeoutExpired('private', 30)) as run:
                with self.assertRaises(system_node.SystemNodeError) as caught:
                    system_node.discover_node()
            self.assertEqual(caught.exception.code, 'system_node_timeout')
            self.assertEqual(run.call_count, 1)

    def test_windows_registry_and_default_locations_are_discovery_candidates(self):
        from scripts.launcher import system_node
        with patch.object(sys, 'platform', 'win32'), \
             patch.object(system_node, '_path_candidates', return_value=[]), \
             patch.object(system_node, '_windows_candidates', return_value=[Path('/registry/node.exe')]) as windows:
            self.assertEqual(list(system_node._candidates()), [Path('/registry/node.exe')])
        windows.assert_called_once()

    def test_windows_registry_install_path_and_standard_program_files_are_searched(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            registry = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2,
                                       KEY_WOW64_64KEY=256, KEY_WOW64_32KEY=512, KEY_READ=1,
                                       OpenKey=lambda *args: nullcontext('key'),
                                       QueryValueEx=lambda *args: (str(root / 'registered'), 1))
            with patch.dict(sys.modules, {'winreg': registry}), \
                 patch.dict(os.environ, {'ProgramFiles': str(root / 'programs'),
                                         'LOCALAPPDATA': str(root / 'local')}):
                candidates = list(system_node._windows_candidates())
            self.assertIn(root / 'registered/node.exe', candidates)
            self.assertIn(root / 'programs/nodejs/node.exe', candidates)
            self.assertIn(root / 'local/Programs/nodejs/node.exe', candidates)


class SelectedNodeToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='system tools ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / 'home'
        self.node = self.root / 'system node/node.exe'
        self.node.parent.mkdir()
        self.node.write_text('operator-trusted fixture')
        self.python = self.root / 'system-python.exe'
        self.python.write_text('operator-trusted fixture')
        self.npm = self.node.parent / 'node_modules/npm/bin/npm-cli.js'
        self.npm.parent.mkdir(parents=True)
        self.npm.write_text('operator-trusted npm fixture')
        self.catalog = {}
        for name, version, executable in (('python', '3.11.18', 'python/python.exe'),
                                          ('node', '22.23.4', 'node/node.exe'),
                                          ('npm', '10.9.4', 'package/bin/npm-cli.js')):
            archive = self.root / (name + '.zip')
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr(executable, name)
            self.catalog[name] = Artifact(name, version, archive.name, 'https://example.com/' + archive.name,
                                          hashlib.sha256(archive.read_bytes()).hexdigest(), 'zip', executable)
        self.fetches = []

    def fetch(self, artifact, cache, settings):
        self.fetches.append(artifact.name)
        destination = cache / artifact.filename
        shutil.copyfile(self.root / artifact.filename, destination)
        return destination

    def patches(self, npm):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(toolchain, 'load_catalog', return_value=self.catalog))
        stack.enter_context(patch.object(toolchain, 'fetch_artifact', side_effect=self.fetch))
        stack.enter_context(patch.object(toolchain, '_check_version'))
        stack.enter_context(patch('scripts.launcher.system_python.validate_python', return_value=self.python))
        stack.enter_context(patch('scripts.launcher.system_node.validate_node', return_value=self.node))
        stack.enter_context(patch('scripts.launcher.system_node.find_npm_cli', return_value=npm))
        return stack

    def test_system_node_and_matching_npm_do_not_request_their_archives(self):
        with self.patches(self.npm):
            values = toolchain.ensure_toolchain(self.home, SourceSettings(), python_executable=self.python,
                                               node_executable=self.node)
            self.assertEqual(self.fetches, [])
            self.assertEqual(values['AWCENTER_MANAGED_NODE'], str(self.node))
            self.assertEqual(values['AWCENTER_MANAGED_NPM_CLI'], str(self.npm))
            self.assertTrue(all(check['status'] == 'ready' for check in toolchain.inspect_toolchain(
                self.home, python_executable=self.python, node_executable=self.node)))
            self.assertEqual(toolchain.toolchain_environment(self.home, python_executable=self.python,
                                                            node_executable=self.node), values)

    def test_missing_matching_system_npm_acquires_only_npm_and_survives_restart(self):
        with self.patches(None):
            values = toolchain.ensure_toolchain(self.home, SourceSettings(), python_executable=self.python,
                                               node_executable=self.node)
            self.assertEqual(self.fetches, ['npm'])
            self.assertEqual(values['AWCENTER_MANAGED_NODE'], str(self.node))
            self.assertTrue(Path(values['AWCENTER_MANAGED_NPM_CLI']).is_file())
            checks = toolchain.inspect_toolchain(self.home, python_executable=self.python, node_executable=self.node)
            self.assertTrue(all(check['status'] == 'ready' for check in checks), checks)
            self.assertEqual(toolchain.toolchain_environment(self.home, python_executable=self.python,
                                                            node_executable=self.node), values)
        self.assertFalse(toolchain._directory(self.home, self.catalog['node']).exists())

    @unittest.skipUnless(HOST_NODE, 'A local Node executable is required for real npm probe tests')
    def test_installed_npm_eleven_does_not_acquire_any_runtime_archive(self):
        from scripts.launcher import system_node
        node = Path(HOST_NODE).resolve()
        self.npm.write_text('console.log("11.18.0")')
        with patch.object(toolchain, 'load_catalog', return_value=self.catalog), \
             patch.object(toolchain, 'fetch_artifact', side_effect=self.fetch), \
             patch.object(toolchain, '_check_version'), \
             patch('scripts.launcher.system_python.validate_python', return_value=self.python), \
             patch.object(system_node, 'validate_node', return_value=node), \
             patch.object(system_node, '_npm_candidates', return_value=[self.npm]):
            values = toolchain.ensure_toolchain(self.home, SourceSettings(), python_executable=self.python,
                                               node_executable=node)
            self.assertEqual(self.fetches, [])
            self.assertEqual(values['AWCENTER_MANAGED_NPM_CLI'], str(self.npm))
            self.assertTrue(all(check['status'] == 'ready' for check in toolchain.inspect_toolchain(
                self.home, python_executable=self.python, node_executable=node)))
            self.assertEqual(toolchain.toolchain_environment(self.home, python_executable=self.python,
                                                            node_executable=node), values)

    def test_invalid_selected_node_fails_before_writes_or_fetches(self):
        from scripts.launcher.system_node import SystemNodeError
        with patch('scripts.launcher.system_node.validate_node', side_effect=SystemNodeError('version')), \
             patch.object(toolchain, 'fetch_artifact') as fetch:
            with self.assertRaises(SystemNodeError):
                toolchain.ensure_toolchain(self.home, SourceSettings(), node_executable=self.node)
        fetch.assert_not_called()
        self.assertFalse(self.home.exists())

    def test_invalid_saved_node_blocks_restart_and_does_not_use_managed_node(self):
        from scripts.launcher.system_node import SystemNodeError
        with self.patches(None), patch('scripts.launcher.system_node.validate_node', side_effect=SystemNodeError('version')):
            checks = toolchain.inspect_toolchain(self.home, python_executable=self.python, node_executable=self.node)
            self.assertEqual(next(item for item in checks if item['name'] == 'node')['status'], 'invalid')
            with self.assertRaises(LauncherError):
                toolchain.toolchain_environment(self.home, python_executable=self.python, node_executable=self.node)
        self.assertEqual(self.fetches, [])

    def test_inspection_preserves_cancellation(self):
        with self.patches(None), patch('scripts.launcher.system_node.validate_node', side_effect=process.OperationCancelled('stop')):
            with self.assertRaises(process.OperationCancelled):
                toolchain.inspect_toolchain(self.home, python_executable=self.python, node_executable=self.node)

    def test_switching_managed_and_system_node_preserves_authenticated_npm_files(self):
        with self.patches(None):
            toolchain.ensure_toolchain(self.home, SourceSettings())
            values = toolchain.ensure_toolchain(self.home, SourceSettings(), python_executable=self.python,
                                               node_executable=self.node)
            self.assertEqual(values['AWCENTER_MANAGED_NODE'], str(self.node))
            self.assertEqual(Path(values['AWCENTER_MANAGED_NPM_CLI']).read_text(), 'npm')
            toolchain.ensure_toolchain(self.home, SourceSettings())
            self.assertTrue(all(check['status'] == 'ready' for check in toolchain.inspect_toolchain(self.home)))

    def test_external_node_npm_receipt_cannot_authorize_tampered_wrapper(self):
        with self.patches(None):
            toolchain.ensure_toolchain(self.home, SourceSettings(), python_executable=self.python,
                                       node_executable=self.node)
            target = toolchain._directory(self.home, self.catalog['npm'])
            wrapper = target / 'bin/npm.cmd'
            wrapper.write_text('injected command')
            receipt_path = target / toolchain.RECEIPT
            receipt = json.loads(receipt_path.read_text())
            receipt['files']['bin/npm.cmd'] = hashlib.sha256(wrapper.read_bytes()).hexdigest()
            receipt_path.write_text(json.dumps(receipt))
            checks = toolchain.inspect_toolchain(self.home, python_executable=self.python, node_executable=self.node)
            self.assertEqual(next(item for item in checks if item['name'] == 'npm')['status'], 'invalid')
            with self.assertRaises(LauncherError):
                toolchain.ensure_toolchain(self.home, SourceSettings(), python_executable=self.python,
                                           node_executable=self.node)


if __name__ == '__main__':
    unittest.main()
