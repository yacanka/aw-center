"""Reuse a backend snapshot within one decision, never across lease boundaries."""
import unittest
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.launcher import installation, installation_profiles as profiles
from scripts.launcher import installation_dependencies as packages
from scripts.manager import ensure, inspection, operations
from scripts import test_manager_ensure as fixtures


class InspectionReuseTests(unittest.TestCase):
    setUp = fixtures.EnsureTests.setUp
    args = fixtures.EnsureTests.args

    def prepared(self):
        profile = profiles.provision_profile(self.project, 'dev', self.home)
        self.project.python.parent.mkdir(parents=True, exist_ok=True)
        self.project.python.touch()
        modules = self.project.frontend / 'node_modules'
        modules.mkdir()
        (modules / '.package-lock.json').write_text('{}', encoding='utf-8')
        (modules / 'vite.cjs').write_bytes(b'installed frontend')
        lock = self.project.frontend / 'package-lock.json'
        lock.write_text('{}', encoding='utf-8')
        packages.dependency_stage(self.project.venv, self.project.requirements, lambda: None)
        packages.dependency_stage(modules, lock, lambda: None)
        return profile

    def test_changed_frontend_lock_routes_only_frontend_to_preparation(self):
        self.prepared()
        (self.project.frontend / 'package-lock.json').write_text('{"new":true}')
        result = self.inspect({'schema': 'ready', 'admin_exists': True})
        self.assertEqual(result['status'], 'incomplete')
        checks = {row['name']: row['status'] for row in result['checks']}
        self.assertEqual(checks['frontend-packages'], 'missing')
        self.assertEqual(checks['python-packages'], 'ready')
        with patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]):
            self.assertTrue(ensure.needs_preparation(self.project, self.args()))

    def test_corrupt_python_output_is_reported_before_any_django_probe(self):
        self.prepared()
        self.project.python.write_bytes(b'changed')
        result = self.inspect({'schema': 'ready', 'admin_exists': True}, probes=0)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(next(row['status'] for row in result['checks']
                              if row['name'] == 'python-packages'), 'invalid')

    def test_removed_node_output_is_detected_even_with_hidden_npm_lock(self):
        self.prepared()
        (self.project.frontend / 'node_modules/vite.cjs').unlink()
        result = self.inspect({'schema': 'ready', 'admin_exists': True})
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(next(row['status'] for row in result['checks']
                              if row['name'] == 'frontend-packages'), 'invalid')

    def test_missing_python_receipt_never_runs_legacy_environment_to_inspect(self):
        self.prepared()
        (self.project.venv / '.awcenter-packages.json').unlink()
        result = self.inspect({'schema': 'ready', 'admin_exists': True}, probes=0)
        self.assertEqual(result['status'], 'incomplete')

    def test_damaged_frontend_reports_action_without_entering_provision(self):
        self.prepared()
        (self.project.frontend / 'node_modules/vite.cjs').unlink()
        events = []
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
             patch.object(installation, 'backend_inspection', return_value={'schema': 'ready', 'admin_exists': True}), \
             patch.object(installation, 'provision', side_effect=AssertionError('unexpected package preparation')):
            operations.execute({'action': 'ensure', 'source_root': str(self.project.root)},
                               events.append, lambda: None, threading.Event())
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'installed_packages_invalid', events)
        self.assertIn('node_modules', error['remedy'])

    def test_invalid_dependency_is_a_blocker_in_the_manager_check_report(self):
        from scripts.manager.view_model import ManagerState
        self.prepared()
        (self.project.frontend / 'node_modules/vite.cjs').unlink()
        result = self.inspect({'schema': 'ready', 'admin_exists': True})
        state = ManagerState()
        state.handle_event({'type': 'checks', 'checks': result['checks']})
        self.assertEqual(next(row['status'] for row in state.checks
                              if row['name'] == 'frontend-packages'), 'ENGEL')

    def test_one_backend_process_per_preparation_decision(self):
        self.prepared()
        state = {'schema': 'ready', 'admin_exists': True, 'auto_migrate_safe': True}
        with patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
             patch.object(installation, 'backend_inspection', return_value=state) as probe:
            self.assertFalse(ensure.needs_preparation(self.project, self.args()))
        probe.assert_called_once()

    def test_claimed_decision_rechecks_changed_database(self):
        self.prepared()
        ready = {'schema': 'ready', 'admin_exists': True, 'auto_migrate_safe': True}
        pending = {**ready, 'schema': 'pending'}
        args = self.args()
        with patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
             patch.object(installation, 'backend_inspection', side_effect=[ready, pending]) as probe, \
             patch.object(operations, '_run_lifecycle') as start:
            self.assertFalse(ensure.needs_preparation(self.project, args))
            with self.assertRaises(ensure.Replan):
                ensure.claimed(self.project, 'start', args, lambda _: None)
        self.assertEqual(probe.call_count, 2)
        start.assert_not_called()

    def test_ready_open_verifies_installed_bytes_and_probes_once_under_the_lease(self):
        self.prepared()
        state = {'schema': 'ready', 'admin_exists': True, 'auto_migrate_safe': True}
        events = []
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
             patch.object(packages, '_package_inventory', wraps=packages._package_inventory) as inventories, \
             patch.object(installation, 'backend_inspection', return_value=state) as probe, \
             patch.object(installation, 'provision') as provision, \
             patch.object(installation, 'start_profile') as start:
            operations.execute({'action': 'ensure', 'source_root': str(self.project.root)},
                               events.append, lambda: None, threading.Event())
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(probe.call_count, 1)
        self.assertEqual([call.args[0] for call in inventories.call_args_list],
                         [self.project.venv, self.project.frontend / 'node_modules'])
        provision.assert_not_called()
        start.assert_called_once()

    def inspect(self, state, *, probes=1):
        events = []
        probe = Mock(return_value=state)
        with patch.object(inspection, 'installation_home', return_value=self.home), \
             patch.object(inspection, 'require_windows'), \
             patch.object(operations, '_project_for', return_value=self.project), \
             patch.object(inspection, 'inspect_toolchain', return_value=[]), \
             patch.object(installation, 'backend_inspection', probe):
            inspection.inspect_profile(self.args(), events.append)
        self.assertEqual(probe.call_count, probes)
        return events[-1]

    def test_profile_inspection_uses_one_consistent_backend_result(self):
        self.prepared()
        event = self.inspect({'schema': 'ready', 'admin_exists': True})
        self.assertEqual(event['status'], 'stopped')
        self.assertTrue(all(row['status'] == 'ready' for row in event['checks']))

    def test_failed_backend_inspection_still_blocks_existing_database(self):
        profile = self.prepared()
        database = Path(profiles.read_profile_environment(profile)['DATABASE_URL'].removeprefix('sqlite:///'))
        database.touch()
        event = self.inspect({'schema': 'error', 'admin_exists': None})
        self.assertEqual(event['status'], 'blocked')
        database_check = next(row for row in event['checks'] if row['name'] == 'database')
        self.assertEqual(database_check['status'], 'blocked')

    def test_core_checks_without_snapshot_still_inspect_backend(self):
        profile = self.prepared()
        with patch.object(installation, 'backend_inspection',
                          return_value={'schema': 'ready', 'admin_exists': True}) as probe:
            checks = installation._core_checks(self.project, profile)
        probe.assert_called_once()
        self.assertTrue(all(row['status'] == 'ready' for row in checks))

    def test_doctor_reports_bad_runtime_without_starting_backend_or_feature_checks(self):
        self.prepared()
        for status in ('invalid', 'missing'):
            runtime = [{'name': 'Python', 'status': status, 'detail': 'Runtime requires attention.'}]
            with self.subTest(status=status), \
                 patch.object(installation, 'installation_home', return_value=self.home), \
                 patch.object(installation, 'inspect_toolchain', return_value=runtime), \
                 patch('scripts.launcher.installation_features.inspect_features',
                       side_effect=AssertionError('feature checks used an unavailable runtime')), \
                 patch.object(installation, 'backend_inspection', side_effect=AssertionError('executed unverified runtime')):
                checks = installation.doctor(self.project, 'dev')
                self.assertEqual(checks[0], {'name': 'Python', 'status': 'blocked', 'detail': 'Runtime requires attention.'})
                self.assertEqual([(row['name'], row['status']) for row in checks[1:]], [('profile', 'ready')])
