"""Offline install bundle integrity regressions; no network downloads."""
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher.model import LauncherError, Project
from scripts.launcher.installation_sources import SourceSettings


def project_at(root):
    (root / 'backend').mkdir(parents=True)
    (root / 'frontend').mkdir()
    (root / 'backend/manage.py').write_text('# synthetic source\n')
    (root / 'requirements.txt').write_text('example==1\n')
    (root / 'frontend/package.json').write_text('{"packageManager":"npm@10.9.4"}')
    (root / 'frontend/package-lock.json').write_text('{"lockfileVersion":3}')
    (root / 'AWCenter.cmd').write_text('@echo off\n')
    (root / 'launcher.py').write_text('# synthetic launcher\n')
    (root / 'scripts/launcher').mkdir(parents=True)
    (root / 'scripts/launcher/installation_sources.py').write_text('# synthetic source adapter\n')
    (root / 'scripts/launcher/installation_catalog.json').write_text('{}')
    for name in ('installation_python.sha256', 'installation_python_startup.sha256'):
        (root / 'scripts/launcher' / name).write_text('synthetic inventory')
    (root / 'scripts/launcher/installation_verify_python.py').write_text('# synthetic verifier\n')
    return Project(root, root / 'backend/manage.py', root / 'frontend/package.json', root / 'requirements.txt')


class BundleSafetyTests(unittest.TestCase):
    def setUp(self):
        self.bundle = importlib.import_module('scripts.launcher.installation_bundle')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        from scripts.launcher.installation_permissions import secure_path
        secure_path(self.root)
        self.project = project_at(self.root / 'project')

    def test_output_must_be_outside_every_additional_input_tree(self):
        for name in ('media', 'assets', 'dependencies'):
            parent = self.root / name
            parent.mkdir()
            marker = parent / 'keep.txt'
            marker.write_text('keep')
            with self.subTest(name=name), self.assertRaises(LauncherError):
                self.bundle.validate_bundle_output(self.project, parent / 'new-bundle', input_roots=(parent,))
            self.assertEqual(list(parent.iterdir()), [marker])

    def test_asset_overlap_is_rejected_before_asset_copy_or_validation(self):
        assets = self.root / 'approved-assets'
        assets.mkdir()
        with patch.object(self.bundle, '_require_windows_target', return_value={}), \
             patch.object(self.bundle, 'verify_asset_source', side_effect=AssertionError('Unsafe overlapping input was read')):
            with self.assertRaises(LauncherError):
                self.bundle.prepare_install_bundle(self.project, assets / 'new-bundle',
                                                   SourceSettings(mode='offline'), assets=assets)
        self.assertEqual(list(assets.iterdir()), [])

    def test_isolated_npm_timeout_tries_the_next_permitted_registry(self):
        import subprocess
        from scripts.launcher.installation_dependencies import PackageTimeoutError
        registries = []
        def capture(command, project, overrides):
            registry = command[command.index('--registry') + 1]
            registries.append(registry)
            if registry == 'https://selected.example/npm':
                raise PackageTimeoutError()
            cache = Path(command[command.index('--cache') + 1]) / '_cacache'
            cache.mkdir(parents=True)
            (cache / 'verified-package').write_bytes(b'package')
            return subprocess.CompletedProcess(command, 0, '', '')
        with patch.object(self.bundle, '_capture', side_effect=capture), \
             patch.object(self.bundle, '_offline_source', return_value=None), \
             patch.object(self.bundle, '_npm_argv', return_value=['npm']):
            target = self.root / 'npm-output'
            self.bundle._acquire_npm(self.project, target, SourceSettings(mode='restricted',
                npm_registry_url='https://selected.example/npm'), {})
        self.assertEqual(registries, ['https://selected.example/npm', 'https://registry.npmjs.org'])
        self.assertEqual((target / '_cacache/verified-package').read_bytes(), b'package')

    def test_pip_build_timeout_is_terminal_without_another_source(self):
        from scripts.launcher.installation_dependencies import PackageTimeoutError
        with patch.object(self.bundle, '_capture', side_effect=PackageTimeoutError()) as capture, \
             patch.object(self.bundle, '_offline_source', return_value=None):
            with self.assertRaises(PackageTimeoutError):
                self.bundle._acquire_wheels(self.project, self.root / 'wheels', SourceSettings(
                    mode='restricted', python_index_url='https://selected.example/simple'), {})
        self.assertEqual(capture.call_count, 1)

    def test_source_copy_excludes_live_environment_and_generates_safe_template(self):
        (self.project.backend / '.env.production').write_text('SECRET_KEY=private-value')
        (self.project.backend / '.env').write_text('OTHER_SECRET=private-value')
        (self.project.root / 'AWCenter.cmd').write_text('@echo off\n')
        output = self.root / 'source'
        self.bundle.copy_install_source(self.project, output)
        self.assertTrue((output / 'AWCenter.cmd').is_file())
        self.assertFalse((output / 'backend/.env.production').exists())
        self.assertFalse((output / 'backend/.env').exists())
        template = (output / 'backend/.env.production.sample').read_text()
        self.assertIn('SECRET_KEY=', template)
        self.assertNotIn('private-value', template)

    def test_source_copy_excludes_package_manager_credentials(self):
        (self.project.root / '.npmrc').write_text('//registry.example/:_authToken=secret-value')
        (self.project.root / '.pypirc').write_text('password=secret-value')
        output = self.root / 'safe-source'
        self.bundle.copy_install_source(self.project, output)
        self.assertFalse((output / '.npmrc').exists())
        self.assertFalse((output / '.pypirc').exists())

    def test_source_checksum_policy_is_relative_to_bundle_not_parent_directory_names(self):
        bundle = self.root / 'dist'
        self.bundle.copy_install_source(self.project, bundle / 'source')
        paths = {item['path'] for item in self.bundle.install_inventory(bundle, source_state=True)}
        self.assertIn('source/backend/manage.py', paths)
        self.assertIn('source/backend/.env.production.sample', paths)

    def test_source_checkout_can_be_packaged_without_git_on_path(self):
        (self.project.root / '.git').mkdir()
        output = self.root / 'safe-source'
        with patch.object(self.bundle.shutil, 'which', return_value=None):
            self.bundle.copy_install_source(self.project, output)
        self.assertTrue((output / 'backend/manage.py').is_file())

    def test_source_copy_rejects_directory_symlink_before_copy(self):
        (self.project.backend / 'linked').symlink_to(self.root, target_is_directory=True)
        output = self.root / 'output'
        with self.assertRaises(LauncherError):
            self.bundle.copy_install_source(self.project, output)
        self.assertFalse(output.exists())

    def test_inventory_rejects_directory_symlink(self):
        tree = self.root / 'tree'
        tree.mkdir()
        (tree / 'link').symlink_to(self.project.root, target_is_directory=True)
        with self.assertRaises(LauncherError):
            self.bundle.install_inventory(tree)

    def test_assets_reject_traversal_and_unlisted_files(self):
        assets = self.root / 'assets'
        assets.mkdir()
        (assets / 'asset-manifest.json').write_text(json.dumps({
            'format_version': 1, 'asset_set': 'approved-v1',
            'artifacts': [{'path': '../outside', 'sha256': 'a'*64, 'size': 1}],
        }))
        with self.assertRaises(LauncherError):
            self.bundle.verify_asset_source(assets)
        (assets / 'asset-manifest.json').write_text(json.dumps({
            'format_version': 1, 'asset_set': 'approved-v1', 'artifacts': [],
        }))
        (assets / 'unlisted.docx').write_bytes(b'private')
        with self.assertRaises(LauncherError):
            self.bundle.verify_asset_source(assets)

    def test_verify_bundle_fails_closed_before_any_install_action(self):
        target = self.root / 'bundle'
        target.mkdir()
        (target / 'install-manifest.json').write_text('{}')
        before = list(target.iterdir())
        with self.assertRaises(LauncherError):
            self.bundle.verify_install_bundle(self.project, target)
        self.assertEqual(before, list(target.iterdir()))

    def test_prepare_rejects_non_windows_target_before_output_mutation(self):
        target = self.root / 'bundle'
        with patch.object(self.bundle, 'target_metadata', return_value={
            'system': 'linux', 'machine': 'x86_64', 'python': '3.11', 'implementation': 'cpython',
        }):
            with self.assertRaises(LauncherError):
                self.bundle.prepare_install_bundle(self.project, target, None)
        self.assertFalse(target.exists())

    def test_output_admission_is_read_only_and_preserves_existing_paths(self):
        validate = getattr(self.bundle, 'validate_bundle_output', None)
        self.assertTrue(callable(validate), 'Bundle output preflight must be reusable before tool setup')
        destination = self.root / 'new-parent/bundle'
        self.assertEqual(validate(self.project, destination), destination)
        self.assertFalse(destination.parent.exists())
        existing = self.root / 'existing'
        existing.mkdir()
        (existing / 'keep.txt').write_text('preserve this output')
        before = self.bundle.install_inventory(self.root)
        for output in (existing, self.project.root, self.project.root / 'bundle'):
            with self.subTest(output=output):
                with self.assertRaises(LauncherError):
                    validate(self.project, output)
        self.assertEqual(self.bundle.install_inventory(self.root), before)

    def test_output_admission_rejects_linked_parent_without_creating_output(self):
        validate = getattr(self.bundle, 'validate_bundle_output', None)
        self.assertTrue(callable(validate), 'Bundle output preflight must enforce unlinked paths')
        link = self.root / 'linked'
        link.symlink_to(self.project.root, target_is_directory=True)
        with self.assertRaises(LauncherError):
            validate(self.project, link / 'bundle')
        self.assertFalse((self.project.root / 'bundle').exists())

    def test_output_admission_normalizes_dot_segments_before_source_scope_check(self):
        with self.assertRaises(LauncherError):
            self.bundle.validate_bundle_output(self.project, self.root / 'outside/../project/bundle')
        output = self.bundle.validate_bundle_output(self.project, self.project.root / '../bundle')
        self.assertEqual(output, self.root / 'bundle')
        self.assertFalse(output.exists())

    def test_complete_bundle_roundtrip_and_tamper_rejection(self):
        from scripts.launcher.installation_sources import Artifact, SourceSettings
        from scripts.launcher.offline_manifest import artifact_metadata, lock_metadata
        catalog = {}
        offline = self.root / 'runtime-source'
        offline.mkdir()
        for name, version in (('python','3.11.18'), ('node','22.23.4'), ('npm','10.9.4')):
            payload = (name + '-reviewed-runtime').encode()
            filename = name + '.zip'
            (offline / filename).write_bytes(payload)
            catalog[name] = Artifact(name, version, filename,
                                     'https://publisher.example/' + filename,
                                     hashlib.sha256(payload).hexdigest(), 'zip', name + '.exe')
        target = {'system':'windows', 'machine':'amd64', 'python':'3.11', 'implementation':'cpython'}
        def dependencies(project, directory, settings):
            (directory / 'wheels').mkdir(parents=True)
            (directory / 'wheels/approved.whl').write_bytes(b'wheel')
            (directory / 'npm-cache').mkdir()
            (directory / 'npm-cache/approved').write_bytes(b'node package')
            value = {'format_version':1, 'target':target,
                     'toolchain':{'python':'3.11.18', 'pip':'25.1', 'node':'v22.23.4', 'npm':'10.9.4'},
                     'locks':lock_metadata(project, self.bundle.Scope()),
                     'artifacts':artifact_metadata(directory)}
            (directory / 'manifest.json').write_text(json.dumps(value))
        native_payload = b'approved native runtime'
        (offline / 'ffmpeg.zip').write_bytes(native_payload)
        approved_features = self.root / 'approved-features.json'
        approved_features.write_text(json.dumps({'format_version':1, 'artifacts':[{
            'name':'ffmpeg', 'version':'1.0', 'filename':'ffmpeg.zip',
            'url':'https://publisher.example/ffmpeg.zip',
            'sha256':hashlib.sha256(native_payload).hexdigest(),
            'archive':'zip', 'executable':'bin/ffmpeg.exe',
        }]}))
        from scripts.launcher.installation_permissions import secure_path
        secure_path(approved_features)
        assets = self.root / 'approved-assets'
        (assets / 'document-templates').mkdir(parents=True)
        template_payload = b'approved DOCX template'
        (assets / 'document-templates/cover.docx').write_bytes(template_payload)
        (assets / 'asset-manifest.json').write_text(json.dumps({
            'format_version':1, 'asset_set':'approved-v1', 'artifacts':[{
                'path':'document-templates/cover.docx', 'size':len(template_payload),
                'sha256':hashlib.sha256(template_payload).hexdigest(),
            }]}))
        from scripts.manager.payload import prepare_source_payload
        from scripts.manager.distribution import seal_distribution, verify_distribution
        manager = self.root / 'manager'
        prepare_source_payload(self.project, manager / 'source')
        (manager / '_internal').mkdir()
        (manager / '_internal/python311.dll').write_bytes(b'embedded fixture')
        (manager / 'AWCenterManager.exe').write_bytes(b'manager fixture')
        seal_distribution(manager)
        output = self.root / 'bundle'
        with patch.object(self.bundle, 'target_metadata', return_value=target), \
             patch('scripts.launcher.offline_manifest.target_metadata', return_value=target), \
             patch.object(self.bundle, '_catalog', return_value=catalog), \
             patch.object(self.bundle, '_prepare_dependencies', side_effect=dependencies), \
             patch('scripts.launcher.installation_sources._retrieve', return_value=False):
            self.assertEqual(self.bundle.prepare_install_bundle(
                self.project, output, SourceSettings(offline_dir=offline), assets=assets,
                feature_catalog=approved_features, manager_distribution=manager), output)
            self.assertEqual(self.bundle.verify_install_bundle(self.project, output)['format_version'], 1)
            self.assertTrue(verify_distribution(output)['complete'])
            self.assertTrue((output / 'AWCenterManager.exe').is_file())
            self.assertTrue((output / 'dependencies/manifest.json').is_file())
            self.assertTrue((output / 'runtimes/python.zip').is_file())
            self.assertTrue((output / 'runtimes/ffmpeg.zip').is_file())
            self.assertTrue((output / 'assets/approved-v1/document-templates/cover.docx').is_file())
            (output / 'source/.venv').mkdir()
            (output / 'source/.venv/generated').write_bytes(b'venv state')
            (output / 'source/backend/db.sqlite3').write_bytes(b'local business state')
            (output / 'source/frontend/node_modules').mkdir()
            (output / 'source/frontend/node_modules/generated.js').write_text('dependency')

            self.bundle.verify_install_bundle(self.project, output)
            code = output / 'source/backend/manage.py'
            original = code.read_text()
            code.write_text('tampered source')
            with self.assertRaises(LauncherError):
                self.bundle.verify_install_bundle(self.project, output)
            code.write_text(original)
            injected = output / 'source/backend/injected.py'
            injected.write_text('unlisted source code')
            with self.assertRaises(LauncherError):
                self.bundle.verify_install_bundle(self.project, output)
            injected.unlink()
            extra = output / 'unexpected.exe'
            extra.write_bytes(b'unlisted executable')
            with self.assertRaises(LauncherError):
                self.bundle.verify_install_bundle(self.project, output)
            extra.unlink()
            lock = self.project.requirements.read_text()
            self.project.requirements.write_text('changed==2\n')
            with self.assertRaises(LauncherError):
                self.bundle.verify_install_bundle(self.project, output)
            self.project.requirements.write_text(lock)
            (output / 'runtimes/python.zip').write_bytes(b'tampered runtime')
            with self.assertRaises(LauncherError):
                self.bundle.verify_install_bundle(self.project, output)
        self.assertFalse(self.project.venv.exists())

    def test_extracted_source_rejects_unknown_private_json_from_distribution(self):
        (self.project.backend / 'project-configuration.json').write_text('{"private":"secret-value"}')
        (self.project.backend / 'unknown-business-data.json').write_text('{"private":"secret-value"}')
        output = self.root / 'safe-source'
        self.bundle.copy_install_source(self.project, output)
        self.assertFalse((output / 'backend/project-configuration.json').exists())
        self.assertFalse((output / 'backend/unknown-business-data.json').exists())

    def test_offline_smoke_does_not_modify_distributed_npm_cache(self):
        cache = self.root / 'cache'
        cache.mkdir()
        (cache / 'package').write_bytes(b'approved cached package')
        before = self.bundle.install_inventory(cache)
        def run(command, **kwargs):
            if '--cache' in command:
                used_cache = Path(command[command.index('--cache') + 1])
                (used_cache / 'npm-log').write_bytes(b'new npm state')
            return type('Completed', (), {'returncode':0})()
        with patch('scripts.launcher.process.required_tool', return_value='npm'), \
             patch.object(self.bundle.subprocess, 'run', side_effect=run):
            self.bundle._verify_npm_offline(self.project, cache, {})
        self.assertEqual(self.bundle.install_inventory(cache), before)

    def test_install_dependency_provenance_works_without_git(self):
        provenance = self.bundle.source_provenance(self.project)
        self.assertRegex(provenance, r'^source-sha256:[0-9a-f]{64}$')
        (self.project.backend / 'manage.py').write_text('changed source')
        self.assertNotEqual(self.bundle.source_provenance(self.project), provenance)

    def test_bundle_refuses_missing_bootstrap_before_download_or_output_mutation(self):
        (self.project.root / 'AWCenter.cmd').unlink()
        target = {'system':'windows', 'machine':'amd64', 'python':'3.11', 'implementation':'cpython'}
        with patch.object(self.bundle, 'target_metadata', return_value=target):
            with self.assertRaises(LauncherError):
                self.bundle.prepare_install_bundle(self.project, self.root / 'bundle', None)
        self.assertFalse((self.root / 'bundle').exists())

    def test_dedicated_dependency_preparation_is_git_free_and_never_distributes_logs(self):
        from scripts.launcher.installation_sources import SourceSettings
        trust_paths = set()
        def capture(command, project, overrides):
            bundle = Path(overrides['PIP_CERT'])
            self.assertTrue(bundle.is_file())
            self.assertEqual(overrides['NPM_CONFIG_CAFILE'], str(bundle))
            self.assertEqual(overrides['NODE_EXTRA_CA_CERTS'], str(bundle))
            trust_paths.add(bundle)
            stdout = ''
            if 'wheel' in command:
                wheelhouse = Path(command[command.index('--wheel-dir') + 1])
                (wheelhouse / 'approved.whl').write_bytes(b'synthetic wheel')
            if 'ci' in command and '--ignore-scripts' in command:
                self.assertNotEqual(project.root, self.project.root)
                self.assertFalse((project.root / '.npmrc').exists())
                cache = Path(command[command.index('--cache') + 1])
                (cache / '_cacache').mkdir(parents=True)
                (cache / '_cacache/package').write_bytes(b'synthetic package')
                (cache / '_logs').mkdir()
                (cache / '_logs/private-log').write_text('credential=private-value')
            if command[-1] == '--version':
                if '-m' in command:
                    stdout = 'pip 25.1 from private-path (python 3.11)'
                elif command[0] == 'node':
                    stdout = 'v22.23.4'
                elif command[0] == 'npm':
                    stdout = '10.9.4'
                else:
                    stdout = 'Python 3.11.18'
            return type('Completed', (), {'returncode':0, 'stdout':stdout, 'stderr':''})()
        (self.project.frontend / '.npmrc').write_text('credential=private-value')
        directory = self.root / 'dependencies'
        with patch.object(self.bundle, '_capture', side_effect=capture), \
             patch.object(self.bundle, '_npm_argv', return_value=['npm']), \
             patch('scripts.launcher.process.required_tool', return_value='node'):
            self.bundle._prepare_dependencies(self.project, directory, SourceSettings())
        manifest = json.loads((directory / 'manifest.json').read_text())
        self.assertRegex(manifest['commit'], r'^source-sha256:[0-9a-f]{64}$')
        self.assertTrue((directory / 'wheels/approved.whl').exists())
        self.assertTrue((directory / 'npm-cache/_cacache/package').exists())
        self.assertFalse((directory / 'npm-cache/_logs').exists())
        self.assertTrue(trust_paths)
        self.assertTrue(all(not path.exists() for path in trust_paths))
        self.assertFalse(list(directory.rglob('*.pem')))
        self.assertNotIn('private-path', json.dumps(manifest))
        self.assertFalse(self.project.venv.exists())
        self.assertFalse((self.project.frontend / 'node_modules').exists())

    def test_python_package_fallback_happens_only_for_availability_failures(self):
        from scripts.launcher.installation_sources import SourceSettings
        calls = []
        def capture(command, project, overrides):
            calls.append(command)
            if '--index-url' in command and 'https://pypi.org/simple' in command:
                return type('Completed', (), {'returncode':1, 'stdout':'', 'stderr':'NewConnectionError'})()
            if 'wheel' in command:
                wheelhouse = Path(command[command.index('--wheel-dir') + 1])
                (wheelhouse / 'approved.whl').write_bytes(b'synthetic wheel')
            return type('Completed', (), {'returncode':0, 'stdout':'', 'stderr':''})()
        with patch.object(self.bundle, '_capture', side_effect=capture):
            self.bundle._acquire_wheels(self.project, self.root / 'wheels',
                                        SourceSettings(python_index_url='https://selected.example/simple'), {})
        self.assertIn('https://pypi.org/simple', calls[0])
        self.assertIn('https://selected.example/simple', calls[1])
        self.assertTrue((self.root / 'wheels/approved.whl').exists())
        certificate_failure = type('Completed', (), {'returncode':1, 'stdout':'', 'stderr':'SSL certificate verification failed'})()
        with patch.object(self.bundle, '_capture', return_value=certificate_failure) as run:
            with self.assertRaises(LauncherError):
                self.bundle._acquire_wheels(self.project, self.root / 'rejected-wheels',
                                            SourceSettings(python_index_url='https://selected.example/simple'), {})
        self.assertEqual(run.call_count, 1)
        self.assertFalse((self.root / 'rejected-wheels').exists())

    def _local_dependency_source(self):
        from scripts.launcher.offline_manifest import artifact_metadata, lock_metadata, target_metadata
        source = self.root / 'local-dependencies'
        (source / 'wheels').mkdir(parents=True)
        (source / 'wheels/approved.whl').write_bytes(b'approved local wheel')
        (source / 'npm-cache/_cacache').mkdir(parents=True)
        (source / 'npm-cache/_cacache/approved').write_bytes(b'approved local npm content')
        manifest = {'format_version': 1, 'target': target_metadata(),
                    'locks': lock_metadata(self.project, self.bundle.Scope()),
                    'artifacts': artifact_metadata(source)}
        (source / 'manifest.json').write_text(json.dumps(manifest))
        return source

    def test_bundle_dependency_acquisition_prefers_verified_local_packages_in_every_mode(self):
        from scripts.launcher.installation_sources import SourceSettings
        source = self._local_dependency_source()
        before = self.bundle.install_inventory(source)
        def capture(command, project, overrides):
            self.assertNotIn('--index-url', command, 'Validated local wheels must avoid the network')
            self.assertNotIn('--registry', command, 'Validated local npm cache must avoid the network')
            return type('Completed', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
        with patch.object(self.bundle, '_capture', side_effect=capture), \
             patch.object(self.bundle, '_npm_argv', return_value=['npm']):
            for mode in ('online', 'corporate', 'restricted', 'offline'):
                with self.subTest(mode=mode):
                    settings = SourceSettings(mode=mode, offline_dir=source)
                    wheels, npm = self.root / (mode + '-wheels'), self.root / (mode + '-npm')
                    self.bundle._acquire_wheels(self.project, wheels, settings, {})
                    self.bundle._acquire_npm(self.project, npm, settings, {})
                    self.assertEqual((wheels / 'approved.whl').read_bytes(), b'approved local wheel')
                    self.assertEqual((npm / '_cacache/approved').read_bytes(), b'approved local npm content')
        self.assertEqual(self.bundle.install_inventory(source), before)

    def test_corrupt_local_bundle_dependencies_are_rejected_before_network_fallback(self):
        from scripts.launcher.installation_sources import SourceSettings
        source = self._local_dependency_source()
        (source / 'wheels/approved.whl').write_bytes(b'corrupt local wheel')
        with patch.object(self.bundle, '_capture', side_effect=AssertionError('Corrupt local media must fail closed')), \
             patch.object(self.bundle, '_npm_argv', return_value=['npm']):
            for acquire in (self.bundle._acquire_wheels, self.bundle._acquire_npm):
                with self.subTest(acquire=acquire.__name__):
                    output = self.root / acquire.__name__
                    with self.assertRaises(LauncherError):
                        acquire(self.project, output, SourceSettings(offline_dir=source), {})
                    self.assertFalse(output.exists())

    def test_bundle_package_acquisition_tries_selected_source_after_proxy_rejection(self):
        from scripts.launcher.installation_sources import SourceSettings
        settings = SourceSettings(python_index_url='https://selected.example/simple',
                                  npm_registry_url='https://selected.example/npm')
        def capture(command, project, overrides):
            if any(url in command for url in ('https://pypi.org/simple', 'https://registry.npmjs.org')):
                return type('Completed', (), {'returncode': 1, 'stdout': '',
                                             'stderr': 'HTTP error 407 Proxy Authentication Required'})()
            if 'wheel' in command:
                directory = Path(command[command.index('--wheel-dir') + 1])
                (directory / 'approved.whl').write_bytes(b'selected source wheel')
            if 'ci' in command:
                cache = Path(command[command.index('--cache') + 1]) / '_cacache'
                cache.mkdir(parents=True)
                (cache / 'approved').write_bytes(b'selected source npm content')
            return type('Completed', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
        with patch.object(self.bundle, '_capture', side_effect=capture), \
             patch.object(self.bundle, '_npm_argv', return_value=['npm']):
            try:
                self.bundle._acquire_wheels(self.project, self.root / 'wheels', settings, {})
                self.bundle._acquire_npm(self.project, self.root / 'npm', settings, {})
            except LauncherError:
                self.fail('Proxy rejection must allow the other explicitly permitted package source')
        self.assertEqual((self.root / 'wheels/approved.whl').read_bytes(), b'selected source wheel')
        self.assertEqual((self.root / 'npm/_cacache/approved').read_bytes(), b'selected source npm content')

    def test_bundle_package_failures_preserve_safe_actionable_categories(self):
        from scripts.launcher.installation_sources import SourceSettings
        for message, code in (
            ('SSL certificate verification failed', 'package_tls_failed'),
            ('hash mismatch', 'package_integrity_failed'),
            ('No space left on device', 'package_disk_full'),
            ('Permission denied', 'package_access_denied'),
            ('Unexpected package-manager failure', 'package_command_failed'),
        ):
            for acquire in (self.bundle._acquire_wheels, self.bundle._acquire_npm):
                with self.subTest(message=message, acquire=acquire.__name__):
                    progress = []
                    result = type('Completed', (), {'returncode': 1, 'stdout': 'private-command-output',
                                                   'stderr': message + ' private-diagnostic'})()
                    output = self.root / 'rejected-packages'
                    with patch.object(self.bundle, '_capture', return_value=result), \
                         patch.object(self.bundle, '_npm_argv', return_value=['npm']):
                        with self.assertRaises(LauncherError) as failed:
                            acquire(self.project, output, SourceSettings(progress=progress.append), {})
                    self.assertEqual(getattr(failed.exception, 'code', None), code)
                    self.assertTrue(getattr(failed.exception, 'remedy', ''))
                    self.assertNotIn('private-', str(failed.exception) + failed.exception.remedy + str(progress))
                    self.assertFalse(output.exists())

    def test_prepare_rejects_unapproved_native_catalog_before_output_mutation(self):
        target = {'system':'windows', 'machine':'amd64', 'python':'3.11', 'implementation':'cpython'}
        catalog = self.root / 'feature-catalog.json'
        catalog.write_text('{"format_version":1,"artifacts":[{"command":"unsafe"}]}')
        from scripts.launcher.installation_permissions import secure_path
        secure_path(catalog)
        output = self.root / 'bundle'
        with patch.object(self.bundle, 'target_metadata', return_value=target):
            with self.assertRaises(LauncherError):
                self.bundle.prepare_install_bundle(self.project, output, None, feature_catalog=catalog)
        self.assertFalse(output.exists())

    def test_offline_npm_smoke_runs_scripts_and_build_in_isolated_tree(self):
        (self.root / 'cache').mkdir()
        completed = type('Completed', (), {'returncode':0})()
        with patch('scripts.launcher.process.required_tool', return_value='npm'), \
             patch.object(self.bundle.subprocess, 'run', return_value=completed) as run:
            self.bundle._verify_npm_offline(self.project, self.root / 'cache', {})
        self.assertEqual(run.call_count, 2)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn('--offline', commands[0])
        self.assertNotIn('--ignore-scripts', commands[0])
        self.assertEqual(commands[1], ['npm', 'run', 'build'])
        self.assertNotEqual(run.call_args_list[0].kwargs['cwd'], self.project.frontend)


class HostRuntimeBundleTests(unittest.TestCase):
    def setUp(self):
        from scripts.launcher.installation_permissions import secure_path
        from scripts.launcher.installation_sources import Artifact, SourceSettings
        from scripts.launcher.offline_manifest import artifact_metadata, lock_metadata
        self.bundle = importlib.import_module('scripts.launcher.installation_bundle')
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        secure_path(self.root)
        self.project = project_at(self.root / 'project')
        self.target = {'system': 'windows', 'machine': 'amd64', 'python': '3.11',
                       'implementation': 'cpython'}
        self.versions = {'python': '3.11.18', 'pip': '25.1', 'node': 'v22.23.4', 'npm': '10.9.4'}
        self.offline = self.root / 'runtime-source'
        self.offline.mkdir()
        self.catalog = {}
        for name, version in (('python', '3.11.18'), ('node', '22.23.4'), ('npm', '10.9.4')):
            payload = (name + '-reviewed-runtime').encode()
            filename = name + '.zip'
            (self.offline / filename).write_bytes(payload)
            self.catalog[name] = Artifact(name, version, filename,
                                          'https://publisher.example/' + filename,
                                          hashlib.sha256(payload).hexdigest(), 'zip', name + '.exe')
        self.settings = SourceSettings(offline_dir=self.offline)

        def dependencies(project, directory, settings):
            (directory / 'wheels').mkdir(parents=True)
            (directory / 'wheels/approved.whl').write_bytes(b'wheel')
            (directory / 'npm-cache').mkdir()
            (directory / 'npm-cache/approved').write_bytes(b'node package')
            value = {'format_version': 1, 'target': self.target, 'toolchain': self.versions.copy(),
                     'locks': lock_metadata(project, self.bundle.Scope()),
                     'artifacts': artifact_metadata(directory)}
            (directory / 'manifest.json').write_text(json.dumps(value))

        for patcher in (
            patch.object(self.bundle, 'target_metadata', return_value=self.target),
            patch('scripts.launcher.offline_manifest.target_metadata', return_value=self.target),
            patch.object(self.bundle, '_catalog', return_value=self.catalog),
            patch.object(self.bundle, '_prepare_dependencies', side_effect=dependencies),
            patch('scripts.launcher.installation_sources._retrieve', return_value=False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def prepare(self, *, external=frozenset(), name='bundle'):
        return self.bundle.prepare_install_bundle(
            self.project, self.root / name, self.settings, external_runtimes=external)

    def manifest(self, output):
        return json.loads((output / 'install-manifest.json').read_text())

    def rewrite_manifest(self, output, value, *, refresh_inventory=False):
        if refresh_inventory:
            value['artifacts'] = self.bundle.install_inventory(
                output, exclude=('install-manifest.json',), source_state=True)
        (output / 'install-manifest.json').write_text(json.dumps(value))

    def test_system_tools_omit_all_runtime_fetches_and_export_only_versions(self):
        self.versions.update(python='3.11.17', node='v24.4.0')
        for path in self.offline.iterdir():
            path.unlink()
        with patch('scripts.launcher.installation_sources.fetch_artifact',
                   side_effect=AssertionError('host tools must not fetch runtime archives')):
            output = self.prepare(external=frozenset({'python', 'node', 'npm'}))
        manifest = self.bundle.verify_install_bundle(self.project, output)
        self.assertEqual(manifest['format_version'], 2)
        self.assertEqual(manifest['host_runtimes'], {
            'python': '3.11.17', 'node': 'v24.4.0', 'npm': '10.9.4'})
        self.assertEqual(manifest['runtimes'], {})
        self.assertFalse((output / 'runtimes').exists())
        self.assertNotIn(str(self.root), json.dumps(manifest))

    def test_partial_host_tools_keep_only_pinned_included_runtime(self):
        self.versions.update(python='3.11.17', node='v24.0.0')
        (self.offline / 'python.zip').unlink()
        (self.offline / 'node.zip').unlink()
        output = self.prepare(external=frozenset({'python', 'node'}))
        manifest = self.bundle.verify_install_bundle(self.project, output)
        self.assertEqual(manifest['host_runtimes'], {'python': '3.11.17', 'node': 'v24.0.0'})
        self.assertEqual(set(manifest['runtimes']), {'npm'})
        self.assertEqual([path.name for path in (output / 'runtimes').iterdir()], ['npm.zip'])
        self.assertEqual((output / 'runtimes/npm.zip').read_bytes(), b'npm-reviewed-runtime')

    def test_prepare_rejects_unknown_host_names_before_output_or_download(self):
        for names in ({'ffmpeg'}, {'python', 'unknown'}, {'node', None}, 'node'):
            with self.subTest(names=names), self.assertRaises(LauncherError):
                self.prepare(external=names)
            self.assertFalse((self.root / 'bundle').exists())

    def test_external_node_accepts_supported_non_catalog_stable_versions(self):
        for index, version in enumerate(('v22.13.0', 'v22.99.1', '24.0.0', 'v25.1.2')):
            with self.subTest(version=version):
                self.versions['node'] = version
                output = self.prepare(external=frozenset({'node'}), name=f'bundle-{index}')
                self.assertEqual(self.manifest(output)['host_runtimes'], {'node': version})

    def test_external_npm_accepts_reviewed_stable_versions_and_roundtrips_host_metadata(self):
        for index, version in enumerate(('10.9.5', '10.10.0', '11.0.0', '11.18.0')):
            with self.subTest(version=version):
                self.versions['npm'] = version
                output = self.prepare(external=frozenset({'npm'}), name=f'bundle-{index}')
                manifest = self.bundle.verify_install_bundle(self.project, output)
                self.assertEqual(manifest['host_runtimes'], {'npm': version})
                self.assertEqual(set(manifest['runtimes']), {'python', 'node'})
                self.assertFalse((output / 'runtimes/npm.zip').exists())

    def test_host_versions_reject_unsupported_prerelease_and_path_values(self):
        cases = (
            ('python', '3.12.0'), ('python', '3.11.1rc1'), ('python', '/private/python'),
            ('node', 'v22.11.9'), ('node', 'v23.0.0'), ('node', 'v24.0.0-rc.1'),
            ('node', 'v24.0.0+private-path'), ('node', {'executable': '/private/node'}),
            ('npm', '10.9.3'), ('npm', '10.8.99'), ('npm', '9.9.9'), ('npm', '12.0.0'),
            ('npm', '11.18.0-rc.1'), ('npm', '11.18.0+private'), ('npm', 'v11.18.0'),
            ('npm', '11.018.0'), ('npm', '/private/npm'), ('npm', 10),
        )
        for name, version in cases:
            with self.subTest(name=name, version=version):
                original = self.versions[name]
                self.versions[name] = version
                with self.assertRaises(LauncherError):
                    self.prepare(external=frozenset({name}))
                self.assertFalse((self.root / 'bundle').exists())
                self.versions[name] = original

    def test_host_metadata_must_be_nonempty_and_exactly_match_omitted_names(self):
        output = self.prepare(external=frozenset({'node'}))
        original = self.manifest(output)
        for host in ({}, None, [], 'node', {'unknown': '24.0.0'},
                     {'node': 'v22.23.4', 'python': '3.11.18'}):
            with self.subTest(host=host):
                self.rewrite_manifest(output, {**original, 'host_runtimes': host})
                with self.assertRaises(LauncherError):
                    self.bundle.verify_install_bundle(self.project, output)

    def test_host_version_tampering_must_match_dependency_toolchain(self):
        output = self.prepare(external=frozenset({'node'}))
        manifest = self.manifest(output)
        manifest['host_runtimes']['node'] = 'v24.0.0'
        self.rewrite_manifest(output, manifest)
        with self.assertRaises(LauncherError):
            self.bundle.verify_install_bundle(self.project, output)

    def test_included_runtime_cannot_be_omitted_or_redeclared_as_host(self):
        output = self.prepare(external=frozenset({'node'}))
        original = self.manifest(output)
        for runtimes in ({}, {**original['runtimes'], 'node': {
                'version': '22.23.4', 'filename': 'node.zip', 'sha256': 'a' * 64}}):
            with self.subTest(runtimes=runtimes):
                self.rewrite_manifest(output, {**original, 'runtimes': runtimes})
                with self.assertRaises(LauncherError):
                    self.bundle.verify_install_bundle(self.project, output)

    def test_missing_included_runtime_is_safe_even_with_rewritten_inventory(self):
        output = self.prepare(external=frozenset({'node'}))
        manifest = self.manifest(output)
        (output / 'runtimes/npm.zip').unlink()
        self.rewrite_manifest(output, manifest, refresh_inventory=True)
        with self.assertRaises(LauncherError) as error:
            self.bundle.verify_install_bundle(self.project, output)
        self.assertNotIn(str(self.root), str(error.exception))

    def test_included_runtime_checksum_remains_pinned_after_inventory_rewrite(self):
        output = self.prepare(external=frozenset({'node'}))
        manifest = self.manifest(output)
        (output / 'runtimes/npm.zip').write_bytes(b'replacement npm archive')
        self.rewrite_manifest(output, manifest, refresh_inventory=True)
        with self.assertRaises(LauncherError):
            self.bundle.verify_install_bundle(self.project, output)

    def test_declared_host_runtime_cannot_carry_an_injected_archive(self):
        output = self.prepare(external=frozenset({'node'}))
        manifest = self.manifest(output)
        (output / 'runtimes/node.zip').write_bytes(b'node-reviewed-runtime')
        self.rewrite_manifest(output, manifest, refresh_inventory=True)
        with self.assertRaises(LauncherError):
            self.bundle.verify_install_bundle(self.project, output)

    def test_version_two_included_toolchain_stays_catalog_pinned(self):
        for name, version in (('python', '3.11.17'), ('npm', '10.9.3'), ('npm', '11.18.0')):
            with self.subTest(name=name):
                original = self.versions[name]
                self.versions[name] = version
                with self.assertRaises(LauncherError):
                    self.prepare(external=frozenset({'node'}))
                self.versions[name] = original

    def test_default_complete_bundle_stays_version_one_without_host_field(self):
        self.versions['python'] = '3.11.17'
        output = self.bundle.prepare_install_bundle(self.project, self.root / 'bundle', self.settings)
        manifest = self.bundle.verify_install_bundle(self.project, output)
        self.assertEqual(manifest['format_version'], 1)
        self.assertNotIn('host_runtimes', manifest)
        self.assertEqual(set(manifest['runtimes']), {'python', 'node', 'npm'})
        self.assertEqual({path.name for path in (output / 'runtimes').iterdir()},
                         {'python.zip', 'node.zip', 'npm.zip'})
        for host in ({}, {'node': 'v22.23.4'}):
            with self.subTest(host=host):
                self.rewrite_manifest(output, {**manifest, 'host_runtimes': host})
                with self.assertRaises(LauncherError):
                    self.bundle.verify_install_bundle(self.project, output)

    def test_complete_bundle_keeps_exact_catalog_node_and_npm_checks(self):
        for name, version in (('node', 'v24.0.0'), ('npm', '10.9.3'), ('npm', '11.18.0')):
            with self.subTest(name=name):
                original = self.versions[name]
                self.versions[name] = version
                with self.assertRaises(LauncherError):
                    self.bundle.prepare_install_bundle(self.project, self.root / 'bundle', self.settings)
                self.versions[name] = original

    def test_version_two_cannot_be_downgraded_or_use_noninteger_version(self):
        output = self.prepare(external=frozenset({'node'}))
        manifest = self.manifest(output)
        for version in (1, True, 2.0, '2'):
            with self.subTest(version=version):
                self.rewrite_manifest(output, {**manifest, 'format_version': version})
                with self.assertRaises(LauncherError):
                    self.bundle.verify_install_bundle(self.project, output)

    def test_offline_host_guard_reports_missing_selected_python_without_paths(self):
        from scripts.launcher.installation_sources import SourceSettings
        output = self.prepare(external=frozenset({'python'}))
        with self.assertRaises(LauncherError) as caught:
            self.bundle.require_bundle_host_runtimes(
                self.project, SourceSettings(mode='offline', offline_dir=output))
        self.assertEqual(caught.exception.code, 'bundle_host_runtime_missing')
        self.assertEqual(caught.exception.artifact, 'python')
        self.assertTrue(caught.exception.remedy)
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_offline_host_guard_accepts_supported_target_versions_different_from_producer(self):
        from scripts.launcher.installation_sources import SourceSettings
        self.versions.update(python='3.11.17', node='v24.4.0')
        output = self.prepare(external=frozenset({'python', 'node', 'npm'}))
        python = self.root / 'target-python.exe'
        node = self.root / 'target-node.exe'
        cli = self.root / 'npm-cli.js'
        # Each validator accepts this target's independently supported version;
        # producer patch versions in the manifest must not become target locks.
        with patch('scripts.launcher.system_python.validate_python', return_value=python), \
             patch('scripts.launcher.system_node.validate_node', return_value=node), \
             patch('scripts.launcher.system_node.find_npm_cli', return_value=cli) as find_npm, \
             patch('scripts.launcher.installation_sources.fetch_artifact',
                   side_effect=AssertionError('guard must not acquire artifacts')):
            self.bundle.require_bundle_host_runtimes(
                self.project, SourceSettings(mode='offline', offline_dir=output),
                python_executable=python, node_executable=node)
        find_npm.assert_called_once_with(node, '10.9.4', compatible=True)

    def test_offline_host_guard_checks_selected_node_and_matching_npm(self):
        from scripts.launcher.installation_sources import SourceSettings
        from scripts.launcher.system_node import SystemNodeError
        output = self.prepare(external=frozenset({'node', 'npm'}))
        settings = SourceSettings(mode='offline', offline_dir=output)
        node = self.root / 'private-node.exe'
        with self.assertRaises(LauncherError) as missing:
            self.bundle.require_bundle_host_runtimes(self.project, settings)
        self.assertEqual(missing.exception.code, 'bundle_host_runtime_missing')
        self.assertEqual(missing.exception.artifact, 'node')
        with patch('scripts.launcher.system_node.validate_node', side_effect=SystemNodeError('version')):
            with self.assertRaises(LauncherError) as incompatible:
                self.bundle.require_bundle_host_runtimes(self.project, settings, node_executable=node)
        self.assertEqual(incompatible.exception.code, 'bundle_host_runtime_missing')
        with patch('scripts.launcher.system_node.validate_node', return_value=node), \
             patch('scripts.launcher.system_node.find_npm_cli', return_value=None):
            with self.assertRaises(LauncherError) as npm_missing:
                self.bundle.require_bundle_host_runtimes(self.project, settings, node_executable=node)
        self.assertEqual(npm_missing.exception.code, 'bundle_host_runtime_missing')
        self.assertEqual(npm_missing.exception.artifact, 'npm')
        self.assertNotIn(str(self.root), str(npm_missing.exception))

    def test_offline_host_guard_rejects_incompatible_selected_python(self):
        from scripts.launcher.installation_sources import SourceSettings
        from scripts.launcher.system_python import SystemPythonError
        output = self.prepare(external=frozenset({'python'}))
        with patch('scripts.launcher.system_python.validate_python',
                   side_effect=SystemPythonError('architecture')):
            with self.assertRaises(LauncherError) as caught:
                self.bundle.require_bundle_host_runtimes(
                    self.project, SourceSettings(mode='offline', offline_dir=output),
                    python_executable=self.root / 'private-python.exe')
        self.assertEqual(caught.exception.code, 'bundle_host_runtime_missing')
        self.assertEqual(caught.exception.artifact, 'python')

    def test_offline_host_guard_fully_verifies_bundle_before_any_host_probe(self):
        from scripts.launcher.installation_sources import SourceSettings
        output = self.prepare(external=frozenset({'node'}))
        (output / 'dependencies/wheels/approved.whl').write_bytes(b'tampered wheel')
        with patch('scripts.launcher.system_node.validate_node') as validate:
            with self.assertRaises(LauncherError) as caught:
                self.bundle.require_bundle_host_runtimes(
                    self.project, SourceSettings(mode='offline', offline_dir=output),
                    node_executable=self.root / 'private-node.exe')
        self.assertFalse(hasattr(caught.exception, 'code'))
        validate.assert_not_called()

    def test_offline_host_guard_supports_local_repository_bundle(self):
        from scripts.launcher.installation_sources import SourceSettings
        output = self.prepare(external=frozenset({'node'}))
        with self.assertRaises(LauncherError) as caught:
            self.bundle.require_bundle_host_runtimes(
                self.project, SourceSettings(mode='offline', repository=output))
        self.assertEqual(caught.exception.code, 'bundle_host_runtime_missing')
        self.assertEqual(caught.exception.artifact, 'node')

    def test_offline_npm_host_requirement_also_needs_a_selected_compatible_node(self):
        from scripts.launcher.installation_sources import SourceSettings
        output = self.prepare(external=frozenset({'npm'}))
        with self.assertRaises(LauncherError) as caught:
            self.bundle.require_bundle_host_runtimes(
                self.project, SourceSettings(mode='offline', offline_dir=output))
        self.assertEqual(caught.exception.code, 'bundle_host_runtime_missing')
        self.assertEqual(caught.exception.artifact, 'npm')

    def test_offline_guard_uses_local_repository_before_fallback_offline_directory(self):
        from scripts.launcher.installation_sources import SourceSettings
        repository = self.prepare(external=frozenset({'node'}), name='repository')
        fallback = self.prepare(external=frozenset({'python'}), name='fallback')
        with self.assertRaises(LauncherError) as caught:
            self.bundle.require_bundle_host_runtimes(
                self.project, SourceSettings(mode='offline', repository=repository,
                                             offline_dir=fallback))
        self.assertEqual(caught.exception.artifact, 'node')

    def test_host_guard_does_not_apply_outside_offline_version_two_bundles(self):
        from scripts.launcher.installation_sources import SourceSettings
        v1 = self.bundle.prepare_install_bundle(self.project, self.root / 'v1', self.settings)
        v2 = self.prepare(external=frozenset({'node'}))
        cases = (SourceSettings(mode='online', offline_dir=v2),
                 SourceSettings(mode='corporate', repository=v2),
                 SourceSettings(mode='offline', offline_dir=v1),
                 SourceSettings(mode='offline', offline_dir=self.offline),
                 SourceSettings(mode='offline', repository='https://publisher.example/bundle'))
        with patch('scripts.launcher.system_python.validate_python') as python, \
             patch('scripts.launcher.system_node.validate_node') as node:
            for settings in cases:
                with self.subTest(settings=settings):
                    self.bundle.require_bundle_host_runtimes(self.project, settings)
        python.assert_not_called()
        node.assert_not_called()

    def test_offline_host_guard_preserves_probe_cancellation(self):
        from scripts.launcher.installation_sources import SourceSettings
        from scripts.launcher.process import OperationCancelled
        output = self.prepare(external=frozenset({'node', 'npm'}))
        settings = SourceSettings(mode='offline', offline_dir=output)
        node = self.root / 'private-node.exe'
        with patch('scripts.launcher.system_node.validate_node', side_effect=OperationCancelled('stopped')):
            with self.assertRaises(OperationCancelled):
                self.bundle.require_bundle_host_runtimes(self.project, settings, node_executable=node)
        with patch('scripts.launcher.system_node.validate_node', return_value=node), \
             patch('scripts.launcher.system_node.find_npm_cli', side_effect=OperationCancelled('stopped')):
            with self.assertRaises(OperationCancelled):
                self.bundle.require_bundle_host_runtimes(self.project, settings, node_executable=node)


if __name__ == '__main__':
    unittest.main()
