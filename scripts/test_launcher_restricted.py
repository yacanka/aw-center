"""Restricted acquisition prefers approved local bytes without relaxing trust."""
import hashlib
import ssl
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.launcher import installation_sources as sources
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project


class RestrictedSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.data = b'approved runtime'
        self.artifact = sources.Artifact('node', '1', 'node.zip',
            'https://public.example/node.zip', hashlib.sha256(self.data).hexdigest(), 'zip', 'node.exe')

    def settings(self):
        return sources.SourceSettings(mode='restricted', offline_dir=self.root / 'local',
                                      repository='https://selected.example/tools')

    def test_local_bytes_prevent_network_even_if_selected_server_rejects_download(self):
        local = self.root / 'local/runtimes'
        local.mkdir(parents=True)
        (local / 'node.zip').write_bytes(self.data)
        with patch.object(sources, '_download', side_effect=AssertionError('network used')):
            result = sources.fetch_artifact(self.artifact, self.root / 'cache', self.settings())
        self.assertEqual(result.read_bytes(), self.data)

    def test_rejected_selected_sources_fall_back_to_public_in_order(self):
        for status in (401, 403, 407, 404):
            attempts = []
            def download(url, target, context):
                attempts.append(url)
                if 'selected.example' in url:
                    raise HTTPError(url, status, 'private body', {}, None)
                target.write_bytes(self.data)
            with self.subTest(status=status), patch.object(sources, '_download', side_effect=download):
                result = sources.fetch_artifact(self.artifact, self.root / str(status), self.settings())
                self.assertEqual(result.read_bytes(), self.data)
                self.assertEqual(attempts, ['https://selected.example/tools/node.zip',
                    'https://selected.example/tools/runtimes/node.zip', self.artifact.url])

    def test_corrupt_local_bytes_do_not_trigger_network_fallback(self):
        local = self.root / 'local'
        local.mkdir()
        (local / 'node.zip').write_bytes(b'corrupt')
        with patch.object(sources, '_download', side_effect=AssertionError('network used')):
            with self.assertRaisesRegex(LauncherError, 'SHA-256'):
                sources.fetch_artifact(self.artifact, self.root / 'cache', self.settings())

    def test_selected_tls_failure_does_not_try_public(self):
        attempts = []
        def fail(url, *_):
            attempts.append(url)
            raise ssl.SSLCertVerificationError('private')
        with patch.object(sources, '_download', side_effect=fail):
            with self.assertRaisesRegex(LauncherError, 'TLS'):
                sources.fetch_artifact(self.artifact, self.root / 'cache', self.settings())
        self.assertEqual(attempts, ['https://selected.example/tools/node.zip'])

    def test_package_indexes_use_selected_then_public_only_in_restricted(self):
        self.assertEqual(sources.acquisition_urls(self.settings(), 'https://public.example',
                         'https://selected.example'), ['https://selected.example', 'https://public.example'])
        self.assertEqual(sources.acquisition_urls(sources.SourceSettings(mode='corporate'),
                         'https://public.example', None), [])


class IndeterminateDiscoveryTests(unittest.TestCase):
    def test_failed_or_malformed_npm_probe_never_means_missing(self):
        from scripts.launcher import system_node
        with tempfile.TemporaryDirectory() as temporary:
            cli = Path(temporary).resolve() / 'npm-cli.js'
            cli.touch()
            for code, output, reason in ((17, '', 'process_failed'), (0, 'not a version', 'invalid_response'),
                                         (0, '', 'invalid_response')):
                with self.subTest(reason=reason, output=output), \
                     patch.object(system_node, '_npm_candidates', return_value=[cli]), \
                     patch.object(system_node, 'controlled_run', return_value=subprocess.CompletedProcess([], code, output, 'private')):
                    with self.assertRaises(system_node.SystemNodeError) as caught:
                        system_node.find_npm_cli(Path('/node'), '10.9.4', compatible=True)
                    self.assertEqual(caught.exception.reason, reason)
                    self.assertNotIn('private', str(caught.exception))

    def test_python_search_stops_when_aggregate_budget_is_exhausted(self):
        from scripts.launcher import system_python as python
        candidates = [[str(self_path)] for self_path in (Path('/candidate-a'), Path('/candidate-b'))]
        with patch.object(python, '_candidates', return_value=candidates), \
             patch.object(python, '_excluded', return_value=False), \
             patch.object(python, '_probe', return_value=None), \
             patch('time.monotonic', side_effect=[0, 0, 121]):
            with self.assertRaises(python.SystemPythonError) as caught:
                python.discover_python()
        self.assertEqual(caught.exception.reason, 'timeout')

    def test_node_search_stops_when_aggregate_budget_is_exhausted(self):
        from scripts.launcher import system_node as node
        with patch.object(node, '_candidates', return_value=[Path('/a'), Path('/b')]), \
             patch.object(node, 'validate_node', side_effect=node.SystemNodeError('version')), \
             patch('time.monotonic', side_effect=[0, 0, 61]):
            with self.assertRaises(node.SystemNodeError) as caught:
                node.discover_node()
        self.assertEqual(caught.exception.reason, 'timeout')

    def test_timeout_cannot_silently_select_managed_runtime(self):
        from scripts.manager import operations
        from scripts.launcher.system_python import SystemPythonError
        from scripts.launcher.system_node import SystemNodeError
        for name, error, choose in (
            ('python', SystemPythonError('timeout'), operations._python_choice),
            ('node', SystemNodeError('timeout'), operations._node_choice),
        ):
            with self.subTest(name=name), patch(f'scripts.launcher.system_{name}.discover_{name}', side_effect=error):
                with self.assertRaises(type(error)):
                    choose(operations.arguments({'action': 'provision'}))


class RestrictedDependenciesTests(unittest.TestCase):
    def test_verified_local_dependencies_skip_all_remote_acquisition(self):
        from scripts.launcher import installation_dependencies as deps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            offline = root / 'offline'
            (offline / 'wheels').mkdir(parents=True)
            (offline / 'npm-cache').mkdir()
            stage = root / 'stage'
            stage.mkdir()
            calls = []
            def execute(command, *_):
                calls.append(command)
                if 'wheel' in command or '--registry' in command:
                    self.fail('Local complete package must not contact a registry')
                return subprocess.CompletedProcess(command, 0, '', '')
            with patch.object(deps, '_offline_dependencies', return_value=offline), \
                 patch.object(deps, '_npm_command', return_value=['npm']), \
                 patch.object(deps, 'capture', side_effect=execute):
                settings = sources.SourceSettings(mode='restricted', offline_dir=offline)
                deps._python_packages(project, settings, {}, stage)
                deps._frontend_packages(project, settings, {}, stage)
            self.assertEqual(len(calls), 3)
            self.assertIn('--no-index', calls[0])
            self.assertIn('--offline', calls[-1])

    def test_rejected_registry_has_isolated_staging_before_public_fallback(self):
        from scripts.launcher import installation_dependencies as deps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            attempts = []
            def execute(command, *_):
                if '--registry' in command:
                    tree = Path(command[command.index('--prefix') + 1])
                    attempts.append((command[command.index('--registry') + 1], tree))
                    self.assertEqual((tree / 'package-lock.json').read_text(), '{}')
                    (tree / 'package-lock.json').write_text('modified by failed registry attempt')
                    return subprocess.CompletedProcess(command, int(len(attempts) == 1), '', 'npm ERR! code E403')
                return subprocess.CompletedProcess(command, 0, '', '')
            with patch.object(deps, '_offline_dependencies', return_value=None), \
                 patch.object(deps, '_npm_command', return_value=['npm']), \
                 patch.object(deps, 'capture', side_effect=execute):
                deps._frontend_packages(project, sources.SourceSettings(mode='restricted',
                    npm_registry_url='https://selected.example/npm'), {}, root)
            self.assertEqual([item[0] for item in attempts], ['https://selected.example/npm', 'https://registry.npmjs.org'])
            self.assertNotEqual(attempts[0][1], attempts[1][1])
            self.assertEqual((project.frontend / 'package-lock.json').read_text(), '{}')
