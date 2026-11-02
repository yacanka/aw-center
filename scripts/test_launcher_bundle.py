"""Offline install bundle integrity regressions; no network downloads."""
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher.model import LauncherError, Project


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
        output = self.root / 'bundle'
        with patch.object(self.bundle, 'target_metadata', return_value=target), \
             patch('scripts.launcher.offline_manifest.target_metadata', return_value=target), \
             patch.object(self.bundle, '_catalog', return_value=catalog), \
             patch.object(self.bundle, '_prepare_dependencies', side_effect=dependencies), \
             patch('scripts.launcher.installation_sources._retrieve', return_value=False):
            self.assertEqual(self.bundle.prepare_install_bundle(
                self.project, output, SourceSettings(offline_dir=offline), assets=assets,
                feature_catalog=approved_features), output)
            self.assertEqual(self.bundle.verify_install_bundle(self.project, output)['format_version'], 1)
            self.assertTrue((output / 'dependencies/manifest.json').is_file())
            self.assertTrue((output / 'runtimes/python.zip').is_file())
            self.assertTrue((output / 'runtimes/ffmpeg.zip').is_file())
            self.assertTrue((output / 'assets/approved-v1/document-templates/cover.docx').is_file())
            (output / 'source/.venv').mkdir()
            (output / 'source/.venv/generated').write_bytes(b'venv state')
            (output / 'source/backend/db.sqlite3').write_bytes(b'local business state')
            (output / 'source/frontend/node_modules').mkdir()
            (output / 'source/frontend/node_modules/generated.js').write_text('dependency')
            (output / 'source/backend/.env').write_text('SECRET_KEY=private-value')
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
        def capture(command, project, overrides):
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


if __name__ == '__main__':
    unittest.main()
