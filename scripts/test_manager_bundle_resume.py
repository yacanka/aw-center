"""Exercise persisted package preparation across distinct Manager invocations."""
from contextlib import ExitStack, nullcontext
import hashlib
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation_bundle as bundle
from scripts.launcher.installation_sources import Artifact, SourceSettings
from scripts.manager import bundle_preparation as prep, distribution
from scripts.manager.paths import startup_values
from scripts.manager.payload import prepare_source_payload
from scripts.test_launcher_bundle import project_at


class ResumablePreparationTests(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.project = project_at(self.root / 'src')
        self.media = self.root / 'manager'
        prepare_source_payload(self.project, self.media / 'source')
        (self.media / '_internal').mkdir()
        (self.media / 'AWCenterManager.exe').write_bytes(b'manager')
        distribution.seal_distribution(self.media)
        self.depot = self.root / 'depot'
        self.depot.mkdir()
        self.catalog = {}
        versions = {'python': '3.11.18', 'node': '22.23.4', 'npm': '10.9.4'}
        for name, version in versions.items():
            data = name.encode()
            item = Artifact(name, version, name + '.zip', 'https://example.org/' + name,
                            hashlib.sha256(data).hexdigest(), 'zip', name + '.exe')
            self.catalog[name] = item
            (self.depot / item.filename).write_bytes(data)
        target = dict(system='windows', machine='amd64', python='3.11', implementation='cpython')
        stack.enter_context(patch.object(bundle, '_catalog', return_value=self.catalog))
        stack.enter_context(patch.object(bundle, 'target_metadata', return_value=target))
        stack.enter_context(patch('scripts.launcher.offline_manifest.target_metadata', return_value=target))
        stack.enter_context(patch('scripts.launcher.installation_sources._retrieve', side_effect=AssertionError('network')))
        stack.enter_context(patch.object(prep.toolchain, '_install', side_effect=lambda home, item, archive, **kw: archive))
        stack.enter_context(patch.object(prep, 'package_trust_environment', side_effect=lambda env, **kw: nullcontext(env)))
        stack.enter_context(patch.object(bundle, '_verify_npm_offline'))
        stack.enter_context(patch.object(bundle, '_component_versions', side_effect=lambda proj, env, kind:
            {'python': versions['python'], 'pip': '25.0'} if kind == 'wheels' else {'node': versions['node'], 'npm': versions['npm']}))
        def wheels(project, directory, settings, env):
            directory.mkdir()
            (directory / 'approved.whl').write_bytes(b'wheel')
        def npm(project, directory, settings, env):
            (directory / '_cacache').mkdir(parents=True)
            (directory / '_cacache/artifact').write_bytes(b'locked package')
        self.acquire_wheels = bundle._acquire_wheels
        self.acquire_npm = bundle._acquire_npm
        self.wheels = stack.enter_context(patch.object(bundle, '_acquire_wheels', side_effect=wheels))
        self.npm = stack.enter_context(patch.object(bundle, '_acquire_npm', side_effect=npm))

    def prepare(self, output='first', hosts=None, imported=None, settings=None):
        return prep.prepare(self.project, self.root / output, settings or SourceSettings(mode='offline', offline_dir=self.depot),
                            self.media, self.root / 'cache', hosts or {}, imported, None, None)

    def test_source_policy_changes_do_not_reuse_previous_packages_or_publication(self):
        def wheels(project, directory, settings, env):
            directory.mkdir()
            (directory / 'approved.whl').write_text(settings.mode + ':' + settings.python_index_url)
        def npm(project, directory, settings, env):
            (directory / '_cacache').mkdir(parents=True)
            (directory / '_cacache/artifact').write_text(settings.mode + ':' + settings.npm_registry_url)
        self.wheels.side_effect = wheels
        self.npm.side_effect = npm
        for number, (mode, index, registry) in enumerate((
                ('restricted', 'https://python-a.example/simple', 'https://npm-a.example'),
                ('corporate', 'https://python-a.example/simple', 'https://npm-a.example'),
                ('corporate', 'https://python-b.example/simple', 'https://npm-a.example'),
                ('corporate', 'https://python-b.example/simple', 'https://npm-b.example'))):
            with self.subTest(mode=mode, index=index, registry=registry):
                settings = SourceSettings(mode=mode, python_index_url=index, npm_registry_url=registry,
                                          runtime_dirs=(self.depot,))
                output = self.prepare(output=f'policy-{number}', settings=settings)
                self.assertEqual((output / 'dependencies/wheels/approved.whl').read_text(), mode + ':' + index)
                self.assertEqual((output / 'dependencies/npm-cache/_cacache/artifact').read_text(), mode + ':' + registry)

    def test_selecting_another_offline_depot_does_not_reuse_old_packages(self):
        def wheels(project, directory, settings, env):
            directory.mkdir()
            (directory / 'approved.whl').write_bytes((settings.offline_dir / 'approved.whl').read_bytes())
        self.wheels.side_effect = wheels
        (self.depot / 'approved.whl').write_bytes(b'first depot')
        self.prepare()
        depot = self.root / 'second-depot'
        depot.mkdir()
        (depot / 'approved.whl').write_bytes(b'second depot')
        output = self.prepare(output='second', settings=SourceSettings(mode='offline', offline_dir=depot))
        self.assertEqual((output / 'dependencies/wheels/approved.whl').read_bytes(), b'second depot')

    def test_node_import_resumes_wheels_then_reuses_verified_publication(self):
        node = self.depot / 'node.zip'
        moved = self.root / node.name
        node.rename(moved)
        with self.assertRaisesRegex(prep.BundleInputsError, 'node.zip'):
            self.prepare()
        self.wheels.assert_called_once()
        self.npm.assert_not_called()
        self.assertFalse((self.root / 'first').exists())
        output = self.prepare(imported=moved)
        self.assertTrue(distribution.verify_distribution(output)['complete'])
        with patch.object(prep, '_prepare_tools', side_effect=AssertionError('warm installation')):
            self.assertEqual(self.prepare(output='AWCenter-offline-second'), output)
        self.wheels.assert_called_once()
        self.npm.assert_called_once()
        moved.write_bytes(b'wrong architecture')
        with self.assertRaisesRegex(prep.BundleInputsError, 'SHA-256'):
            self.prepare(output='third', imported=moved)
        self.assertTrue(distribution.verify_distribution(output)['complete'])

    def test_complete_local_depot_never_runs_registry_or_index_acquisition(self):
        source = self.depot / 'dependencies'
        (source / 'wheels').mkdir(parents=True)
        (source / 'wheels/approved.whl').write_bytes(b'wheel')
        (source / 'npm-cache/_cacache').mkdir(parents=True)
        (source / 'npm-cache/_cacache/pinned').write_bytes(b'npm')
        manifest = {'format_version': 1, 'target': bundle.target_metadata(),
                    'locks': bundle.lock_metadata(self.project, bundle.Scope()),
                    'artifacts': bundle.artifact_metadata(source)}
        (source / 'manifest.json').write_text(json.dumps(manifest))
        self.wheels.side_effect = self.acquire_wheels
        self.npm.side_effect = self.acquire_npm
        def capture(command, project, overrides):
            self.assertIn('--no-index', command)
            self.assertIn('--dry-run', command)
            return subprocess.CompletedProcess(command, 0, '', '')
        with patch.object(bundle, '_capture', side_effect=capture) as calls:
            self.assertTrue(distribution.verify_distribution(self.prepare())['complete'])
        calls.assert_called_once()

    def test_used_media_never_transfers_local_environment(self):
        output = self.prepare()
        (output / 'source/backend/.env').write_text('private local settings')
        other = self.prepare(output='other')
        self.assertNotEqual(output, other)
        self.assertFalse((other / 'source/backend/.env').exists())
        self.wheels.assert_called_once()
        self.npm.assert_called_once()

    def test_target_host_tools_are_explicit_and_start_offline(self):
        with patch('scripts.launcher.system_node.discover_node', return_value=self.root / 'node.exe'), \
             patch('scripts.launcher.system_node.find_npm_cli', return_value=self.root / 'npm-cli.js'):
            output = self.prepare(hosts={'node': None})
        manifest = bundle.verify_install_bundle(self.project, output)
        manager = distribution.verify_distribution(output)
        self.assertFalse(manager['complete'])
        self.assertEqual(manager['host_runtimes'], manifest['host_runtimes'])
        self.assertEqual(set(manifest['host_runtimes']), {'npm', 'node'})
        self.assertEqual(set(manifest['runtimes']), {'python'})
        import sys
        with patch.object(sys, 'executable', str(output / 'AWCenterManager.exe')), patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(startup_values({'source_mode': 'corporate'}, None)['source_mode'], 'offline')
