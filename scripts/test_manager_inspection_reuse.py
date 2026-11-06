"""Reuse a backend snapshot within one decision, never across lease boundaries."""
import unittest
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.launcher import installation, installation_profiles as profiles
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
        return profile

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

    def test_ready_open_reuses_packages_and_checks_backend_once_per_lease_phase(self):
        self.prepared()
        state = {'schema': 'ready', 'admin_exists': True, 'auto_migrate_safe': True}
        events = []
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
             patch.object(installation, 'backend_inspection', return_value=state) as probe, \
             patch.object(installation, 'provision') as provision, \
             patch.object(installation, 'start_profile') as start:
            operations.execute({'action': 'ensure', 'source_root': str(self.project.root)},
                               events.append, lambda: None, threading.Event())
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(probe.call_count, 2)
        provision.assert_not_called()
        start.assert_called_once()

    def inspect(self, state):
        events = []
        probe = Mock(return_value=state)
        with patch.object(inspection, 'installation_home', return_value=self.home), \
             patch.object(inspection, 'require_windows'), \
             patch.object(operations, '_project_for', return_value=self.project), \
             patch.object(inspection, 'inspect_toolchain', return_value=[]), \
             patch.object(installation, 'backend_inspection', probe), \
             patch.object(inspection, 'backend_inspection', probe):
            inspection.inspect_profile(self.args(), events.append)
        probe.assert_called_once()
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
