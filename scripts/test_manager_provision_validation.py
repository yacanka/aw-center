"""Developer preparation avoids repeating completed package inventories."""
from contextlib import ExitStack, nullcontext
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation, installation_dependencies as packages
from scripts.launcher import installation_profiles as profiles
from scripts.launcher.installation_state import private_directory
from scripts.launcher_test_support import create_project
from scripts.manager import operations


class ProvisionValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / 'home'
        for context in (patch.dict(os.environ, {}, clear=True),
                        patch.object(profiles, 'installation_home', return_value=self.home)):
            context.start()
            self.addCleanup(context.stop)

    def prepare_project(self, profile):
        source = self.home / 'r' / '0123456789ab' if profile == 'prod' else self.root / 'source'
        if profile == 'prod':
            private_directory(source, root=self.home)
        else:
            source.mkdir()
        self.project = create_project(source)
        self.project.python.parent.mkdir(parents=True)
        self.project.python.write_bytes(b'installed Python')
        modules = self.project.frontend / 'node_modules'
        vite = modules / 'vite/bin/vite.js'
        vite.parent.mkdir(parents=True)
        vite.write_bytes(b'installed Vite')
        lock = self.project.frontend / 'package-lock.json'
        lock.write_text('{}')
        packages.dependency_stage(self.project.venv, self.project.requirements, lambda: None)
        packages.dependency_stage(modules, lock, lambda: None)

    def provision(self, policy, *, manager_ensure=True, backend_state=None, profile='dev', update_frontend=False):
        self.prepare_project(profile)
        options = {}
        if profile == 'prod':
            certificate, key = self.root / 'cert.pem', self.root / 'key.pem'
            certificate.touch()
            key.touch()
            options = {'host': '192.0.2.10', 'tls_cert_file': certificate, 'tls_key_file': key}
        profiles.provision_profile(self.project, profile, self.home, **options)
        if update_frontend:
            (self.project.frontend / 'package-lock.json').write_text('{"lockfileVersion":3}')
        args = operations.arguments({'action': 'ensure', 'validation_policy': policy, 'profile': profile,
                                     'install_python': True, 'install_node': True,
                                     'source_mode': 'offline'})
        args.manager_ensure = manager_ensure
        args.progress = lambda _: None
        tools = {'AWCENTER_MANAGED_PYTHON': str(self.root / 'managed-python.exe'),
                 'AWCENTER_MANAGED_NODE': str(self.root / 'managed-node.exe')}
        observed = {'schema': 'pending', 'admin_exists': True}
        def initialize(*_):
            observed.update(backend_state or {'schema': 'ready'})
        with ExitStack() as stack:
            stack.enter_context(patch.object(installation, 'require_windows'))
            stack.enter_context(patch.object(installation, 'installation_home', return_value=self.home))
            stack.enter_context(patch.object(installation, 'ensure_toolchain', return_value=tools))
            if profile == 'prod':
                stack.enter_context(patch.object(installation, '_tls_preflight'))
                stack.enter_context(patch.object(installation.runtime, 'validate_tls_identity'))
                stack.enter_context(patch('scripts.launcher.production_build.prepare_build'))
            # Native interpreter validation is unrelated to counting the real
            # completed package stages on this cross-platform fixture.
            stack.enter_context(patch.object(packages, '_prepare_package_venv',
                                             side_effect=lambda *values: values[-1]))
            stack.enter_context(patch.object(installation, '_initialize_schema', side_effect=initialize))
            stack.enter_context(patch.object(installation, '_initial_admin'))
            backend = stack.enter_context(patch.object(installation, 'backend_inspection',
                                                       side_effect=lambda *_: dict(observed)))
            stack.enter_context(patch('scripts.launcher.installation_features.install_features', return_value=[]))
            if update_frontend:
                def install_frontend(project, *_args, **_kwargs):
                    vite = project.frontend / 'node_modules/vite/bin/vite.js'
                    vite.parent.mkdir(parents=True)
                    vite.write_bytes(b'updated Vite')
                stack.enter_context(patch.object(packages, 'package_trust_environment', return_value=nullcontext(tools)))
                stack.enter_context(patch.object(packages, '_frontend_packages', side_effect=install_frontend))
            inventory = stack.enter_context(patch.object(packages, '_package_inventory',
                                                         wraps=packages._package_inventory))
            checks = installation._provision(self.project, args)
        backend.assert_called_once()
        return checks, inventory.call_count

    def test_development_fast_preparation_reuses_both_completed_stages(self):
        checks, inventories = self.provision('developer')
        self.assertEqual(inventories, 0)
        self.assertTrue(all(row['status'] == 'ready' for row in checks), checks)

    def test_development_fast_preparation_updates_only_the_stale_stage(self):
        checks, inventories = self.provision('developer', update_frontend=True)
        self.assertEqual(inventories, 2)
        self.assertEqual((self.project.frontend / 'node_modules/vite/bin/vite.js').read_bytes(), b'updated Vite')
        self.assertTrue(all(row['status'] == 'ready' for row in checks), checks)

    def test_managed_preparation_retains_full_final_package_validation(self):
        checks, inventories = self.provision('managed')
        self.assertEqual(inventories, 4)
        self.assertTrue(all(row['status'] == 'ready' for row in checks), checks)

    def test_production_fast_preparation_reuses_both_completed_stages(self):
        checks, inventories = self.provision('developer', profile='prod')
        self.assertEqual(inventories, 0)
        self.assertTrue(all(row['status'] == 'ready' for row in checks), checks)

    def test_production_fast_preparation_updates_only_the_stale_stage(self):
        checks, inventories = self.provision('developer', profile='prod', update_frontend=True)
        self.assertEqual(inventories, 2)  # Inspect the old frontend tree and record the replacement.
        self.assertEqual((self.project.frontend / 'node_modules/vite/bin/vite.js').read_bytes(), b'updated Vite')
        self.assertTrue(all(row['status'] == 'ready' for row in checks), checks)

    def test_developer_policy_without_manager_ensure_keeps_full_validation(self):
        checks, inventories = self.provision('developer', manager_ensure=False)
        self.assertEqual(inventories, 4)
        self.assertTrue(all(row['status'] == 'ready' for row in checks), checks)

    def test_developer_completion_still_reports_fresh_database_failure(self):
        checks, _ = self.provision('developer', backend_state={'schema': 'error'})
        database = next(row for row in checks if row['name'] == 'database')
        self.assertEqual(database['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
