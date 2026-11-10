"""Full portable media includes its executable and cannot trust stale host paths."""
import importlib
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.launcher.model import LauncherError
from scripts.launcher.installation_sources import Artifact, SourceSettings, fetch_artifact
from scripts.manager.payload import prepare_source_payload
from scripts.test_launcher_bundle import project_at


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = project_at(self.root / 'project')
        self.media = self.root / 'media'
        prepare_source_payload(self.project, self.media / 'source')
        (self.media / '_internal').mkdir()
        (self.media / '_internal/python311.dll').write_bytes(b'embedded runtime fixture')
        (self.media / 'AWCenterManager.exe').write_bytes(b'manager fixture')

    def module(self):
        try:
            return importlib.import_module('scripts.manager.distribution')
        except ModuleNotFoundError:
            self.fail('Full Manager distribution support is missing')

    def test_complete_manifest_detects_missing_or_changed_executable(self):
        distribution = self.module()
        distribution.seal_distribution(self.media)
        distribution.verify_distribution(self.media)
        (self.media / 'AWCenterManager.exe').write_bytes(b'tampered')
        with self.assertRaises(LauncherError):
            distribution.verify_distribution(self.media)

    def test_startup_defaults_use_package_paths_but_preserve_explicit_root(self):
        distribution = self.module()
        (self.media / 'install-manifest.json').write_text('{}')
        distribution.seal_distribution(self.media, complete=True)
        from scripts.manager import paths
        old = {'source_root': 'Z:/old-machine/source', 'offline_dir': 'Z:/old-package', 'source_mode': 'online'}
        with patch.object(paths.sys, 'frozen', True, create=True), \
             patch.object(paths.sys, 'executable', str(self.media / 'AWCenterManager.exe')):
            actual = paths.startup_values(old, None)
            self.assertEqual(actual['source_root'], str(self.media / 'source'))
            self.assertEqual(actual['offline_dir'], str(self.media))
            self.assertEqual(actual['source_mode'], 'offline')
            explicit = self.root / 'operator-source'
            self.assertEqual(paths.startup_values(old, explicit)['source_root'], str(explicit))

    def test_same_media_preserves_advanced_values_and_moved_media_keeps_history(self):
        distribution = self.module()
        (self.media / 'install-manifest.json').write_text('{}')
        distribution.seal_distribution(self.media, complete=True)
        from scripts.manager import paths
        with patch.object(paths.sys, 'frozen', True, create=True), \
             patch.object(paths.sys, 'executable', str(self.media / 'AWCenterManager.exe')):
            initial = paths.startup_values({}, None)
            selected = {**initial, 'source_mode': 'corporate', 'node_command': 'C:/chosen/node.exe',
                        'repository': 'https://packages.example'}
            restored = paths.startup_values(selected, None)
            self.assertEqual(restored['node_command'], 'C:/chosen/node.exe')
            self.assertEqual(restored['source_mode'], 'corporate')
            older = {**selected, '_media_context': 'a' * 64}
            moved = paths.startup_values(older, None)
            self.assertEqual(moved['node_command'], '')
            self.assertEqual(moved['source_mode'], 'corporate')
            self.assertEqual(moved['_contexts']['a' * 64]['node_command'], 'C:/chosen/node.exe')

    def test_distribution_copy_rejects_different_source(self):
        distribution = self.module()
        distribution.seal_distribution(self.media)
        other = self.root / 'other'
        prepare_source_payload(self.project, other / 'source')
        (other / 'source/launcher.py').write_text('different source')
        with self.assertRaises(LauncherError):
            distribution.copy_manager(self.media, other)
        self.assertFalse((other / 'AWCenterManager.exe').exists())

    def test_invalid_output_is_rejected_before_runtime_preparation(self):
        distribution = self.module()
        distribution.seal_distribution(self.media)
        marker = self.root / 'runtime-preparation-started'
        def prepare_tools(home, settings):
            marker.write_text('tools started')
            return {}
        with patch('scripts.launcher.installation.require_windows'), \
             patch('scripts.launcher.toolchain.ensure_toolchain', side_effect=prepare_tools):
            with self.assertRaises(LauncherError):
                distribution.prepare_full_manager(self.project, self.project.root / 'bundle',
                                                  SourceSettings(), self.media)
        self.assertFalse(marker.exists(), 'Invalid output must not start tool preparation')

    def test_output_inside_media_is_rejected_before_any_runtime_preparation(self):
        distribution = self.module()
        distribution.seal_distribution(self.media)
        marker = self.root / 'runtime-started'
        def prepare_tools(home, settings):
            marker.write_text('started')
            return {}
        with patch('scripts.launcher.installation.require_windows'), \
             patch('scripts.launcher.toolchain.ensure_toolchain', side_effect=prepare_tools):
            with self.assertRaises(LauncherError):
                distribution.prepare_full_manager(self.project, self.media / 'new-bundle',
                                                  SourceSettings(mode='offline'), self.media)
        self.assertFalse(marker.exists(), 'Output overlap must be rejected before tools are prepared')
        distribution.verify_distribution(self.media)

    def _prepare_with_runtime_source(self, *, existing_cache, corrupt_cache=False, without_installation=False,
                                     without_distribution=False):
        distribution = self.module()
        bundle = importlib.import_module('scripts.launcher.installation_bundle')
        from scripts.launcher.offline_manifest import artifact_metadata, lock_metadata
        target = {'system': 'windows', 'machine': 'amd64', 'python': '3.11', 'implementation': 'cpython'}
        catalog = {}
        payloads = {}
        home = self.root / 'installation'
        for name, version in (('python', '3.11.18'), ('node', '22.23.4'), ('npm', '10.9.4')):
            payloads[name] = (name + '-reviewed-runtime').encode()
            catalog[name] = Artifact(name, version, name + '.zip',
                                     'https://publisher.example/' + name + '.zip',
                                     hashlib.sha256(payloads[name]).hexdigest(), 'zip', name + '.exe')
        if existing_cache:
            cache = home / 'cache/runtimes'
            cache.mkdir(parents=True)
            for name, payload in payloads.items():
                (cache / catalog[name].filename).write_bytes(payload)
            if corrupt_cache:
                (cache / 'python.zip').write_bytes(b'corrupt cached runtime')
            (home / 'runtimes').mkdir()
            (home / 'runtimes/live-tool.exe').write_bytes(b'active tool must remain unchanged')
        before = bundle.install_inventory(home) if existing_cache else []
        distribution.seal_distribution(self.media)
        connected = True
        def retrieve(url, destination, context):
            if existing_cache or not connected:
                self.fail('Verified cached archives must avoid another network download')
            name = Path(url).stem
            destination.write_bytes(payloads[name])
            return True
        def prepare_tools(temporary_home, settings):
            nonlocal connected
            for artifact in catalog.values():
                fetch_artifact(artifact, temporary_home / 'cache/runtimes', settings)
            connected = False  # The bundle stage must succeed after connectivity is lost.
            return {'AWCENTER_MANAGED_PYTHON': str(temporary_home / 'python.exe')}
        def freeze(project, destination, settings, *, python):
            self.assertEqual(Path(python).name, 'python.exe')
            prepare_source_payload(project, destination / 'source')
            (destination / '_internal').mkdir()
            (destination / '_internal/python311.dll').write_bytes(b'fresh embedded runtime')
            (destination / 'AWCenterManager.exe').write_bytes(b'fresh frozen manager')
            distribution.seal_distribution(destination)
            return destination
        def selected_home():
            if without_installation:
                self.fail('Preparing portable media must not require an existing installation home')
            return home
        def dependencies(project, directory, settings):
            (directory / 'wheels').mkdir(parents=True)
            (directory / 'wheels/approved.whl').write_bytes(b'wheel')
            (directory / 'npm-cache').mkdir()
            (directory / 'npm-cache/approved').write_bytes(b'package')
            manifest = {'format_version': 1, 'target': target,
                        'toolchain': {'python': '3.11.18', 'pip': '25.1', 'node': 'v22.23.4', 'npm': '10.9.4'},
                        'locks': lock_metadata(project, bundle.Scope()), 'artifacts': artifact_metadata(directory)}
            (directory / 'manifest.json').write_text(json.dumps(manifest))
        output = self.root / 'bundle'
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)}), \
             patch('scripts.launcher.installation.require_windows'), \
             patch('scripts.launcher.installation_profiles.installation_home', side_effect=selected_home), \
             patch('scripts.launcher.toolchain.ensure_toolchain', side_effect=prepare_tools), \
             patch('scripts.build_manager.freeze_manager', side_effect=freeze), \
             patch('scripts.launcher.installation_sources._retrieve', side_effect=retrieve), \
             patch.object(bundle, 'target_metadata', return_value=target), \
             patch('scripts.launcher.offline_manifest.target_metadata', return_value=target), \
             patch.object(bundle, '_catalog', return_value=catalog), \
             patch.object(bundle, '_prepare_dependencies', side_effect=dependencies):
            if without_installation:
                os.environ.pop('LOCALAPPDATA')
            distribution.prepare_full_manager(self.project, output, SourceSettings(),
                                              None if without_distribution else self.media)
            self.assertTrue(distribution.verify_distribution(output)['complete'])
            expected_exe = b'fresh frozen manager' if without_distribution else b'manager fixture'
            self.assertEqual((output / 'AWCenterManager.exe').read_bytes(), expected_exe)
            self.assertTrue((output / '_internal/python311.dll').is_file())
        for name, payload in payloads.items():
            self.assertEqual((output / 'runtimes' / catalog[name].filename).read_bytes(), payload)
        if existing_cache:
            self.assertEqual(bundle.install_inventory(home), before)

    def test_bundle_reuses_archives_downloaded_for_its_temporary_tools(self):
        self._prepare_with_runtime_source(existing_cache=False)

    def test_missing_distribution_is_built_from_source_and_complete_bundle_is_verified(self):
        self._prepare_with_runtime_source(existing_cache=False, without_distribution=True)

    def test_bundle_reads_existing_runtime_cache_without_mutating_live_tools(self):
        self._prepare_with_runtime_source(existing_cache=True)

    def test_corrupt_existing_runtime_cache_is_rejected_without_network_fallback(self):
        with self.assertRaisesRegex(LauncherError, 'SHA-256'):
            self._prepare_with_runtime_source(existing_cache=True, corrupt_cache=True)

    def test_portable_preparation_does_not_require_an_existing_installation_home(self):
        self._prepare_with_runtime_source(existing_cache=False, without_installation=True)
