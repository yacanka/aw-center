"""Developer readiness is deliberately smaller than comprehensive integrity."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.launcher import installation, installation_dependencies as dependencies
from scripts.launcher import installation_features as features, toolchain
from scripts.launcher.installation_sources import Artifact
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project


class DeveloperDependencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = create_project(self.root)
        self.frontend = self.project.frontend / 'node_modules'
        self.lock = self.project.frontend / 'package-lock.json'
        self.lock.write_text('{}')
        self.project.python.parent.mkdir(parents=True)
        self.project.python.write_text('python')
        self.vite = self.frontend / 'vite/bin/vite.js'
        self.vite.parent.mkdir(parents=True)
        self.vite.write_text('vite')
        for target, lock in ((self.project.venv, self.project.requirements), (self.frontend, self.lock)):
            dependencies._install_stage(target, lock, lambda: None)
        self.receipts = [target / dependencies._STAGE_RECEIPT for target in (self.project.venv, self.frontend)]

    def fast(self, **options):
        return dependencies.dependency_checks(self.project, developer=True, **options)

    def test_fast_checks_skip_inventory_and_warm_receipt_parse_without_changing_evidence(self):
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.receipts}
        from scripts.launcher import developer_readiness
        original = developer_readiness._json_object
        parsed = []
        def read(path, **options):
            if path in self.receipts:
                parsed.append(path)
            return original(path, **options)
        with patch.object(dependencies, '_package_inventory', side_effect=AssertionError('full inventory')), \
             patch.object(developer_readiness, '_json_object', side_effect=read):
            self.assertTrue(all(row['status'] == 'ready' for row in self.fast()))
            self.assertEqual(parsed, self.receipts)
            parsed.clear()
            self.assertTrue(all(row['status'] == 'ready' for row in self.fast()))
            self.assertEqual(parsed, [])
        self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.receipts})
        self.assertIn('hızlı', self.fast()[0]['detail'].casefold())
        self.assertTrue(list((self.root / '.runtime').rglob('*.json')))
        self.assertTrue(all(row['status'] == 'ready' for row in dependencies.dependency_checks(self.project)))

    def test_changed_bytes_remain_developer_ready_but_managed_checks_fail(self):
        self.fast()
        self.vite.write_text('local edit')
        self.assertEqual(self.fast()[1]['status'], 'ready')
        self.assertEqual(dependencies.dependency_checks(self.project)[1]['status'], 'invalid')
        with self.assertRaises(dependencies.DependencyIntegrityError):
            dependencies.dependency_checks(self.project, fail_invalid=True)

    def test_lock_change_only_invalidates_affected_stage_and_reverting_reuses_it(self):
        self.fast()
        self.lock.write_text('{"changed": true}')
        self.assertEqual([row['status'] for row in self.fast()], ['ready', 'missing'])
        self.lock.write_text('{}')
        self.assertEqual([row['status'] for row in self.fast()], ['ready', 'ready'])

    def test_changed_replaced_or_missing_receipt_cannot_use_cached_readiness(self):
        self.fast()
        receipt = self.receipts[1]
        saved = receipt.read_bytes()
        receipt.write_text('broken')
        self.assertEqual(self.fast()[1]['status'], 'invalid')
        replacement = self.root / 'replacement.json'
        replacement.write_bytes(saved.replace(b'"version": 1', b'"version": 2'))
        replacement.replace(receipt)
        self.assertEqual(self.fast()[1]['status'], 'invalid')
        receipt.unlink()
        self.assertEqual(self.fast()[1]['status'], 'missing')

    def test_missing_required_executables_are_checked_even_with_warm_cache(self):
        self.fast()
        self.project.python.unlink()
        self.vite.unlink()
        self.assertEqual([row['status'] for row in self.fast()], ['missing', 'missing'])

    @unittest.skipIf(os.name == 'nt', 'symlink creation requires host privilege')
    def test_fast_check_rejects_symlinked_required_output_and_cache_location(self):
        self.fast()
        self.vite.unlink()
        self.vite.symlink_to(self.project.python)
        self.assertEqual(self.fast()[1]['status'], 'invalid')
        self.vite.unlink()
        self.vite.write_text('vite')
        import shutil
        shutil.rmtree(self.root / '.runtime')
        outside = self.root / 'outside'
        outside.mkdir()
        (self.root / '.runtime').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(LauncherError):
            self.fast(fail_invalid=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_corrupt_small_cache_is_rebuilt_from_receipts(self):
        self.fast()
        for path in (self.root / '.runtime').rglob('*.json'):
            path.write_text('broken')
        self.assertEqual([row['status'] for row in self.fast()], ['ready', 'ready'])


class DeveloperRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.artifacts = {}
        for name, version, executable in (('python', '3.11.18', 'python/python.exe'),
                                          ('node', '22.23.4', 'node/node.exe'),
                                          ('npm', '10.9.4', 'package/bin/npm-cli.js')):
            artifact = Artifact(name, version, name + '.zip', 'https://example.test/' + name,
                                hashlib.sha256(name.encode()).hexdigest(), 'zip', executable)
            self.artifacts[name] = artifact
            target = toolchain._directory(self.root, artifact)
            path = target / executable
            path.parent.mkdir(parents=True)
            path.write_text(name)
            (target / toolchain.RECEIPT).write_text(json.dumps(
                {'name': name, 'version': version, 'sha256': artifact.sha256, 'files': {}}))

    def test_limited_toolchain_checks_versions_and_receipts_without_inventory(self):
        receipts = list(self.root.rglob(toolchain.RECEIPT))
        before = {path: path.read_bytes() for path in receipts}
        with patch.object(toolchain, 'load_catalog', return_value=self.artifacts), \
             patch.object(toolchain, '_inventory', side_effect=AssertionError('inventory')), \
             patch.object(toolchain, '_trusted_inventory', side_effect=AssertionError('archive inventory')), \
             patch.object(toolchain, '_check_version') as version:
            checks = toolchain.inspect_toolchain(self.root, verify=False)
            self.assertTrue(all(row['status'] == 'ready' for row in checks))
            self.assertEqual(version.call_count, 3)
            self.assertEqual(version.call_args.kwargs['node'],
                             toolchain._directory(self.root, self.artifacts['node']) / self.artifacts['node'].executable)
            environment = toolchain.toolchain_environment(self.root, verify=False)
            self.assertTrue(Path(environment['AWCENTER_MANAGED_PYTHON']).is_file())
        self.assertEqual(before, {path: path.read_bytes() for path in receipts})

    def test_limited_toolchain_rejects_missing_receipt_executable_and_version_mismatch(self):
        with patch.object(toolchain, 'load_catalog', return_value=self.artifacts), \
             patch.object(toolchain, '_check_version') as version:
            (toolchain._directory(self.root, self.artifacts['node']) / toolchain.RECEIPT).unlink()
            self.assertEqual(toolchain.inspect_toolchain(self.root, verify=False)[1]['status'], 'missing')
            (toolchain._directory(self.root, self.artifacts['python']) / self.artifacts['python'].executable).unlink()
            self.assertNotEqual(toolchain.inspect_toolchain(self.root, verify=False)[0]['status'], 'ready')
            version.side_effect = toolchain.RuntimeValidationError('version_mismatch', 'npm')
            self.assertEqual(toolchain.inspect_toolchain(self.root, verify=False)[2]['status'], 'invalid')

    def test_managed_node_does_not_skip_managed_npm_receipt_for_bundled_npm(self):
        npm = self.artifacts['npm']
        (toolchain._directory(self.root, npm) / toolchain.RECEIPT).unlink()
        with patch.object(toolchain, 'load_catalog', return_value=self.artifacts), \
             patch.object(toolchain, '_check_version'), \
             patch('scripts.launcher.system_node.find_npm_cli', return_value=self.root / 'bundled-npm.js') as find:
            self.assertEqual(toolchain.inspect_toolchain(self.root, verify=False)[2]['status'], 'missing')
            find.assert_not_called()

    def test_limited_runtime_probe_cancellation_propagates(self):
        from scripts.launcher.process import OperationCancelled
        with patch.object(toolchain, 'load_catalog', return_value=self.artifacts), \
             patch.object(toolchain, '_check_version', side_effect=OperationCancelled('cancelled')):
            with self.assertRaises(OperationCancelled):
                toolchain.inspect_toolchain(self.root, verify=False)

    @unittest.skipIf(os.name == 'nt', 'symlink creation requires host privilege')
    def test_limited_toolchain_rejects_linked_executable_before_execution(self):
        artifact = self.artifacts['python']
        path = toolchain._directory(self.root, artifact) / artifact.executable
        path.unlink()
        path.symlink_to(__file__)
        with patch.object(toolchain, 'load_catalog', return_value=self.artifacts), \
             patch.object(toolchain, '_check_version') as version:
            self.assertEqual(toolchain.inspect_toolchain(self.root, verify=False)[0]['status'], 'invalid')
        self.assertFalse(any(call.args[0] == path for call in version.call_args_list))

    def test_optional_tool_fast_paths_do_not_inventory_but_managed_paths_detect_changes(self):
        source = self.root / 'source'
        source.mkdir()
        project = create_project(source)
        artifact = Artifact('ffmpeg', '1', 'ffmpeg.zip', 'https://example.test/ffmpeg', 'a' * 64,
                            'zip', 'bin/ffmpeg.exe')
        target = self.root / 'tools/ffmpeg-1'
        path = target / artifact.executable
        path.parent.mkdir(parents=True)
        path.write_text('ffmpeg')
        manifest = {'artifact_sha256': artifact.sha256,
                    'artifacts': features.install_inventory(target)}
        (target / 'tool-manifest.json').write_text(json.dumps(manifest))
        profile = {'installation_home': str(self.root)}
        path.write_text('local edit')
        with patch.object(features, '_catalog_for_home', return_value={'ffmpeg': artifact}):
            with patch.object(features, '_verify_inventory', side_effect=AssertionError('optional inventory')):
                self.assertEqual(features.feature_environment(project, profile, verify=False)['FFMPEG_EXECUTABLE'], str(path))
            self.assertNotIn('FFMPEG_EXECUTABLE', features.feature_environment(project, profile))
            path.unlink()
            self.assertNotIn('FFMPEG_EXECUTABLE', features.feature_environment(project, profile, verify=False))


class DeveloperStartupTests(unittest.TestCase):
    def test_core_checks_use_fast_packages_but_keep_backend_schema_gate(self):
        profile = {'name': 'dev'}
        ready = [{'name': 'python-packages', 'status': 'ready'}, {'name': 'frontend-packages', 'status': 'ready'}]
        with patch.object(installation, 'inspect_profile', return_value=[]), \
             patch.object(installation, 'dependency_checks', return_value=ready) as packages, \
             patch.object(installation, 'backend_inspection', return_value={'schema': 'pending', 'admin_exists': True}) as backend:
            rows = installation._core_checks(SimpleNamespace(), profile, validation_policy='developer')
            self.assertEqual(next(row for row in rows if row['name'] == 'database')['status'], 'blocked')
            self.assertTrue(packages.call_args.kwargs['developer'])
            backend.assert_called_once()

    def test_start_propagates_fast_policy_and_keeps_migration_and_readiness_callbacks(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            project = create_project(Path(temporary))
            profile = {'name': 'dev', 'installation_home': temporary, 'env_file': temporary + '/dev.env',
                       'host': '127.0.0.1', 'backend_port': 8000, 'frontend_port': 5173}
            stack.enter_context(patch.object(installation, 'require_windows'))
            stack.enter_context(patch.object(installation, 'load_profile', return_value=profile))
            stack.enter_context(patch.object(installation, 'profile_environment', return_value={}))
            tools = stack.enter_context(patch.object(toolchain, 'toolchain_environment', return_value={}))
            optional = stack.enter_context(patch.object(features, 'feature_environment', return_value={}))
            django = stack.enter_context(patch.object(installation, '_django'))
            session = stack.enter_context(patch.object(installation, 'runtime_session'))
            session.return_value.__enter__.return_value = project.root
            dev = stack.enter_context(patch.object(installation.runtime, 'dev'))
            installation._start_profile(project, 'dev', validation_policy='developer')
            self.assertFalse(tools.call_args.kwargs['verify'])
            self.assertFalse(optional.call_args.kwargs['verify'])
            self.assertEqual(django.call_args.args[2], ['migrate', '--check'])
            self.assertTrue(callable(dev.call_args.kwargs['ready']))
            self.assertFalse(dev.call_args.kwargs['migrate'])

    def test_unknown_and_production_developer_policy_rejected_before_runtime(self):
        with patch.object(installation, 'require_windows'), \
             patch.object(installation, 'load_profile') as load:
            for function in (installation.start_profile, installation._start_profile):
                for name, policy in (('prod', 'developer'), ('dev', 'unknown')):
                    with self.subTest(function=function.__name__, name=name, policy=policy), self.assertRaises(LauncherError):
                        function(SimpleNamespace(), name, validation_policy=policy)
            load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
