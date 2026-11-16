"""Preliminary planning never replaces source verification under the leases."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation_profiles as profiles, resource_locks
from scripts.launcher.discovery import discover_project
from scripts.launcher.model import LauncherError
from scripts.manager import ensure, operations, payload
from scripts.test_launcher_bundle import project_at


class PreliminarySourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        environment = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        windows = patch('scripts.launcher.installation.require_windows')
        windows.start()
        self.addCleanup(windows.stop)
        self.home = self.root / 'AWCenter'
        self.project = project_at(self.root / 'checkout')
        self.project.package_json.write_text('{"dependencies":{"vue":"3"}}')
        self.media = self.root / 'media'
        payload.prepare_source_payload(self.project, self.media)
        self.release = payload.stage_production_source(self.media, self.home)
        certificate, key = self.root / 'certificate.pem', self.root / 'key.pem'
        certificate.write_text('operator certificate fixture')
        key.write_text('operator key fixture')
        profiles.provision_profile(discover_project(self.release), 'prod', self.home,
                                   host='192.0.2.10', tls_cert_file=certificate, tls_key_file=key)

    def args(self, **values):
        args = operations.arguments({'action': 'ensure', 'profile': 'prod',
                                     'source_root': str(self.release), 'source_selection': 'explicit', **values})
        args.source_root = values.get('source_root', str(self.release))
        args.progress = lambda _: None
        return args

    def test_explicit_media_planning_uses_recorded_release_without_changing_selection(self):
        (self.project.root / 'launcher.py').write_text('# newer distribution\n')
        updated = self.root / 'updated-media'
        payload.prepare_source_payload(self.project, updated)
        args = self.args(source_root=str(updated))
        before = (self.home / 'config/prod.profile.json').read_bytes()
        with patch.object(payload, '_source_inventory', wraps=payload._source_inventory) as inventory, \
             patch('scripts.launcher.discovery.bounded_matches', side_effect=AssertionError('recursive discovery')):
            project = operations._project_for('doctor', args, before_lock=True)
        self.assertEqual(project.root, self.release)
        self.assertEqual(profiles.load_profile(project, 'prod', self.home)['source_root'], str(self.release))
        self.assertEqual(inventory.call_count, 0)
        self.assertEqual(args.source_root, str(updated))
        self.assertEqual(args.source_selection, 'explicit')
        with self.assertRaises(payload.ProductionSourceNotPrepared):
            operations._project_for('start', args)
        self.assertEqual((self.home / 'config/prod.profile.json').read_bytes(), before)

    def test_canonical_preliminary_plan_skips_hashes_but_claimed_dispatch_rechecks_tampering(self):
        args = self.args()
        with patch.object(payload, '_source_inventory', wraps=payload._source_inventory) as inventory, \
             patch.object(ensure, 'needs_preparation', return_value=False):
            self.assertEqual(ensure._initial_action(args), 'start')
        self.assertEqual(inventory.call_count, 0)
        changed = self.release / 'launcher.py'
        changed.write_text('# modified after preliminary plan\n')
        real_inventory = payload._source_inventory
        held_during_scan = []
        def inventory_under_lease(*args, **options):
            held_during_scan.append(bool(resource_locks._held.get()))
            return real_inventory(*args, **options)
        with patch.object(payload, '_source_inventory', side_effect=inventory_under_lease), \
             patch.object(operations, '_lifecycle', side_effect=AssertionError('unchecked lifecycle')):
            with self.assertRaises(LauncherError):
                operations._dispatch('start', args, lambda _: None)
        self.assertEqual(held_during_scan, [True])
        self.assertEqual(changed.read_text(), '# modified after preliminary plan\n')

    def test_packaged_local_preliminary_layout_is_reverified_before_use(self):
        project = discover_project(self.media)
        profiles.provision_profile(project, 'dev', self.home)
        args = self.args(profile='dev', source_root=str(self.media))
        with patch.object(operations.sys, 'frozen', True, create=True), \
             patch.object(payload, '_source_inventory', wraps=payload._source_inventory) as inventory:
            self.assertEqual(operations._project_for('doctor', args, before_lock=True), project)
            self.assertEqual(inventory.call_count, 0)
            project.requirements.write_text('changed==1\n')
            with self.assertRaises(LauncherError):
                operations._project_for('start', args)
        self.assertEqual(inventory.call_count, 1)

    def test_developer_preliminary_and_final_checks_keep_explicit_editable_source(self):
        profiles.provision_profile(discover_project(self.media), 'dev', self.home)
        args = self.args(profile='dev', source_root=str(self.project.root), validation_policy='developer')
        with patch.object(operations.sys, 'frozen', True, create=True), \
             patch.object(payload, '_source_inventory', side_effect=AssertionError('source hash')), \
             patch('scripts.launcher.discovery.bounded_matches', side_effect=AssertionError('recursive discovery')):
            for before_lock in (True, False):
                with self.subTest(before_lock=before_lock):
                    self.assertEqual(operations._project_for('doctor', args, before_lock=before_lock), self.project)
        self.assertEqual(args.source_root, str(self.project.root))
        self.assertEqual(args.source_selection, 'explicit')

    def test_preliminary_source_selection_rejects_oversized_or_malformed_saved_metadata(self):
        path = self.home / 'config/prod.profile.json'
        for content in (b' ' * (64 * 1024 + 1), b'{"name":"prod","source_root":42}'):
            with self.subTest(oversized=len(content) > 64 * 1024):
                path.write_bytes(content)
                with patch.object(payload, '_source_inventory', wraps=payload._source_inventory) as inventory:
                    with self.assertRaises(LauncherError):
                        operations._project_for('doctor', self.args(), before_lock=True)
                self.assertEqual(inventory.call_count, 0)

    @unittest.skipUnless(os.name == 'posix', 'POSIX permissions fixture')
    def test_preliminary_source_selection_keeps_private_profile_requirement(self):
        path = self.home / 'config/prod.profile.json'
        path.chmod(0o644)
        with self.assertRaises(LauncherError):
            operations._project_for('doctor', self.args(), before_lock=True)


if __name__ == '__main__':
    unittest.main()
