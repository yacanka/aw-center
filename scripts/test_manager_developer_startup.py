"""Developer Manager observations never authorize an unchecked startup."""
import threading
import unittest
from unittest.mock import patch

from scripts.launcher import installation, installation_dependencies as packages
from scripts.launcher import installation_profiles as profiles
from scripts.launcher.model import LauncherError
from scripts.manager import ensure, inspection, operations
from scripts import test_manager_inspection_reuse as fixtures


class DeveloperStartupTests(unittest.TestCase):
    setUp = fixtures.InspectionReuseTests.setUp

    def prepared(self):
        profile = profiles.provision_profile(self.project, 'dev', self.home)
        self.project.python.parent.mkdir(parents=True, exist_ok=True)
        self.project.python.touch()
        modules = self.project.frontend / 'node_modules'
        (modules / 'vite/bin').mkdir(parents=True)
        (modules / 'vite/bin/vite.js').write_bytes(b'installed frontend')
        (modules / '.package-lock.json').write_text('{}')
        lock = self.project.frontend / 'package-lock.json'
        lock.write_text('{}')
        packages.dependency_stage(self.project.venv, self.project.requirements, lambda: None)
        packages.dependency_stage(modules, lock, lambda: None)
        return profile

    def args(self, **values):
        args = operations.arguments({'action': 'ensure', 'source_root': str(self.project.root),
                                     'source_selection': 'explicit', 'validation_policy': 'developer', **values})
        args.source_root = str(self.project.root)
        args.progress = lambda _: None
        return args

    def execute(self, **values):
        events = []
        operations.execute({'action': 'ensure', 'source_root': str(self.project.root),
                            'source_selection': 'explicit', 'validation_policy': 'developer', **values},
                           events.append, lambda: None, threading.Event())
        return events

    def test_worker_rejects_invalid_policy_before_storage_or_dispatch(self):
        for values in ({'validation_policy': 'fast'}, {'profile': 'prod'},
                       {'source_selection': 'automatic'}, {'source_root': ''},
                       {'validation_policy': None}):
            with self.subTest(values=values), patch.object(operations, '_dispatch') as dispatch:
                events = self.execute(**values)
                dispatch.assert_not_called()
                self.assertEqual(events[-1], {'type': 'done', 'ok': False}, events)
                self.assertFalse(self.home.exists())

    def test_missing_policy_keeps_managed_default(self):
        self.assertEqual(operations.arguments({'action': 'inspect'}).validation_policy, 'managed')

    def test_inspection_only_reads_bounded_metadata_without_any_probe(self):
        self.prepared()
        events = []
        with patch.object(inspection, 'require_windows'), \
             patch.object(inspection, 'installation_home', return_value=self.home), \
             patch.object(inspection, 'inspect_toolchain', side_effect=AssertionError('runtime probe')), \
             patch.object(inspection, '_core_checks', side_effect=AssertionError('backend checks')), \
             patch.object(packages, '_package_inventory', side_effect=AssertionError('inventory')), \
             patch('scripts.launcher.discovery.bounded_matches', side_effect=AssertionError('source inventory')), \
             patch('scripts.launcher.runtime_selection.tool_choices', side_effect=AssertionError('runtime selection')), \
             patch('scripts.launcher.installation.require_windows'):
            inspection.inspect_profile(self.args(action='inspect'), events.append)
        self.assertEqual(events[-1]['status'], 'stopped')
        self.assertIn('Geliştirici', events[-1]['detail'])
        self.assertIn('hızlı kontrol', events[-1]['detail'])
        self.assertNotIn('başlatılmaya hazır', events[-1]['detail'])

    def test_uninstalled_inspection_does_not_probe_tool_choices(self):
        events = []
        with patch.object(inspection, 'require_windows'), \
             patch.object(inspection, 'installation_home', return_value=self.home), \
             patch('scripts.launcher.runtime_selection.tool_choices', side_effect=AssertionError('runtime selection')):
            inspection.inspect_profile(self.args(action='inspect'), events.append)
        self.assertEqual(events[-1]['status'], 'not_installed')
        self.assertFalse(self.home.exists())

    def test_inspection_rejects_oversized_metadata_before_loading_profile(self):
        self.prepared()
        (self.home / 'config/dev.profile.json').write_bytes(b' ' * (64 * 1024 + 1))
        with patch.object(inspection, 'require_windows'), \
             patch.object(inspection, 'installation_home', return_value=self.home), \
             patch.object(inspection, 'load_profile', side_effect=AssertionError('unbounded read')):
            with self.assertRaises(LauncherError):
                inspection.inspect_profile(self.args(action='inspect'), lambda _: None)

    def test_developer_source_does_not_require_release_equality_or_walk(self):
        for action in ('start', 'inspect', 'doctor', 'provision'):
            with self.subTest(action=action), \
                 patch.object(operations.sys, 'frozen', True, create=True), \
                 patch('scripts.launcher.installation.require_windows'), \
                 patch('scripts.manager.payload.verify_source_payload', side_effect=AssertionError('release equality')), \
                 patch('scripts.launcher.discovery.bounded_matches', side_effect=AssertionError('source inventory')):
                project = operations._project_for(action, self.args())
            self.assertEqual(project, self.project)

    def test_managed_frozen_source_still_requires_release_equality(self):
        with patch.object(operations.sys, 'frozen', True, create=True), \
             patch('scripts.launcher.installation.require_windows'), \
             patch('scripts.manager.payload.verify_source_payload', side_effect=LauncherError('changed')) as verify:
            with self.assertRaises(LauncherError):
                operations._project_for('start', self.args(validation_policy='managed'))
        verify.assert_called_once_with(self.project.root)

    def test_ready_ensure_uses_fresh_backend_without_inventory_or_install(self):
        self.prepared()
        ready = {'schema': 'ready', 'admin_exists': True, 'auto_migrate_safe': True}
        def start_profile(project, name, **options):
            options['on_ready'](profiles.load_profile(project, name, self.home))
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]) as runtime, \
             patch.object(packages, '_package_inventory', side_effect=AssertionError('inventory')), \
             patch.object(installation, 'backend_inspection', return_value=ready) as backend, \
             patch.object(installation, 'provision', side_effect=AssertionError('installation')), \
             patch.object(installation, 'start_profile', side_effect=start_profile) as start:
            events = self.execute()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        backend.assert_called_once()
        self.assertEqual(runtime.call_args.kwargs['verify'], False)
        self.assertEqual(start.call_args.kwargs['validation_policy'], 'developer')
        ready_index = next(index for index, event in enumerate(events) if event['type'] == 'ready')
        metrics = events[ready_index - 1]
        self.assertEqual(metrics['type'], 'startup-work')
        self.assertEqual(metrics['policy'], 'developer')
        self.assertTrue(all(value == 0 for value in metrics['counts'].values()))
        self.assertEqual(next(event['validation_policy'] for event in events if event['type'] == 'resources'),
                         'developer')

    def test_changed_lock_selects_preparation_for_only_affected_dependency(self):
        self.prepared()
        (self.project.frontend / 'package-lock.json').write_text('{"changed":true}')
        with patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
             patch.object(packages, '_package_inventory', side_effect=AssertionError('inventory')), \
             patch.object(installation, 'backend_inspection', return_value={'schema': 'ready', 'admin_exists': True}):
            self.assertTrue(ensure.needs_preparation(self.project, self.args()))
            checks = packages.dependency_checks(self.project, developer=True, verify=False)
        self.assertEqual([(row['name'], row['status']) for row in checks],
                         [('python-packages', 'ready'), ('frontend-packages', 'missing')])

    def test_under_lease_backend_changes_replan_and_do_not_start(self):
        self.prepared()
        args = self.args()
        for changed in ({'schema': 'pending', 'admin_exists': True},
                        {'schema': 'ready', 'admin_exists': False}):
            with self.subTest(changed=changed), \
                 patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
                 patch.object(packages, '_package_inventory', side_effect=AssertionError('inventory')), \
                 patch.object(installation, 'backend_inspection', side_effect=[
                     {'schema': 'ready', 'admin_exists': True}, changed]) as backend, \
                 patch.object(operations, '_run_lifecycle') as start:
                self.assertFalse(ensure.needs_preparation(self.project, args))
                with self.assertRaises(ensure.Replan):
                    ensure.claimed(self.project, 'start', args, lambda _: None)
                self.assertEqual(backend.call_count, 2)
                start.assert_not_called()

    def test_lock_change_after_initial_decision_replans_under_the_lease(self):
        self.prepared()
        args = self.args()
        with patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
             patch.object(packages, '_package_inventory', side_effect=AssertionError('inventory')), \
             patch.object(installation, 'backend_inspection', return_value={'schema': 'ready', 'admin_exists': True}), \
             patch.object(operations, '_run_lifecycle') as start:
            self.assertFalse(ensure.needs_preparation(self.project, args, before_lock=True))
            self.project.requirements.write_text('Django==5.3\n')
            with self.assertRaises(ensure.Replan) as change:
                ensure.claimed(self.project, 'start', args, lambda _: None)
        self.assertEqual(change.exception.action, 'provision')
        start.assert_not_called()

    def test_doctor_request_still_verifies_runtime_and_dependency_bytes(self):
        self.prepared()
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch.object(installation, 'installation_home', return_value=self.home), \
             patch.object(installation, 'inspect_toolchain', return_value=[]) as runtime, \
             patch.object(packages, '_package_inventory', wraps=packages._package_inventory) as inventories, \
             patch.object(installation, 'backend_inspection', return_value={'schema': 'ready', 'admin_exists': True}), \
             patch('scripts.launcher.installation_features.inspect_features', return_value=[]):
            events = self.execute(action='doctor')
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertNotIn('verify', runtime.call_args.kwargs)
        self.assertEqual(len(inventories.call_args_list), 2)


if __name__ == '__main__':
    unittest.main()
