"""Automatic desktop admission preserves files, leases and safe diagnostics."""
from contextlib import nullcontext
import errno
import json
from pathlib import Path
import tempfile
import threading
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher.resource_locks import path_key
from scripts.manager import operations
from scripts.test_launcher_bundle import project_at


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = project_at(self.root / 'source')
        self.project.package_json.write_text('{"dependencies":{"vue":"3"}}')
        self.home = self.root / 'home'

    def execute(self, **values):
        events = []
        with patch('scripts.launcher.installation.require_windows'), \
             patch('scripts.launcher.installation_profiles.installation_home', return_value=self.home):
            operations.execute({'action': 'bundle', 'source_root': str(self.project.root), **values},
                               events.append, lambda: None, threading.Event())
        return events

    def test_missing_source_reports_actual_phase_and_specific_next_step(self):
        missing = self.root / 'private-source-path'
        events = self.execute(source_root=str(missing), output=str(self.root / 'output'))
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'source_unavailable')
        self.assertIn('kayna', error['message'].casefold())
        self.assertNotIn('Hazırlık:', error['message'])
        self.assertNotIn(str(missing), json.dumps(events))

    def test_absent_windows_distribution_continues_to_automatic_preparation(self):
        output = self.root / 'output'
        def prepare(project, destination, settings, distribution, **options):
            self.assertIsNone(distribution)
            destination.mkdir()
            (destination / 'AWCenterManager.exe').write_bytes(b'prepared manager fixture')
        with patch('scripts.manager.distribution.prepare_full_manager', side_effect=prepare):
            events = self.execute(output=str(output))
        self.assertEqual(events[-1], {'type': 'done', 'ok': True})
        self.assertEqual((output / 'AWCenterManager.exe').read_bytes(), b'prepared manager fixture')

    def test_existing_output_directory_is_preserved_and_new_child_is_claimed(self):
        output = self.root / 'selected-output'
        output.mkdir()
        sentinel = output / 'keep.txt'
        sentinel.write_text('keep')
        args = operations.arguments({'action': 'bundle', 'output': str(output)})
        args.source_root, args.progress = str(self.project.root), lambda message: None
        with patch('scripts.launcher.installation_profiles.installation_home', return_value=self.home), \
             patch('scripts.launcher.resource_locks.resource_locks', return_value=nullcontext()) as leases, \
             patch.object(operations, '_dispatch_claimed'):
            operations._dispatch('bundle', args, lambda event: None)
        self.assertEqual(args.output.parent, output)
        self.assertFalse(args.output.exists())
        self.assertEqual(sentinel.read_text(), 'keep')
        self.assertTrue(leases.call_args.args[1][path_key(args.output)])

    def test_worker_can_choose_output_when_request_has_no_target(self):
        args = operations.arguments({'action': 'bundle'})
        args.source_root, args.progress = str(self.project.root), lambda message: None
        with patch('scripts.launcher.installation_profiles.installation_home', return_value=self.home), \
             patch('scripts.launcher.resource_locks.resource_locks', return_value=nullcontext()), \
             patch.object(operations, '_dispatch_claimed'):
            operations._dispatch('bundle', args, lambda event: None)
        self.assertEqual(args.output.parent, self.home / 'exports')
        self.assertFalse(args.output.exists())

    def test_adjacent_distribution_is_found_without_an_extra_form_field(self):
        media = self.project.root.parent
        (media / 'AWCenterManager.exe').write_bytes(b'exe marker')
        (media / 'manager-manifest.json').write_text('{}')
        args = SimpleNamespace(output=self.root / 'output', manager_distribution=None,
                               progress=lambda message: None, assets=None, feature_catalog=None)
        events = []
        with patch('scripts.launcher.installation.source_settings', return_value=SourceSettings()), \
             patch('scripts.manager.distribution.prepare_full_manager', return_value=args.output) as prepare:
            operations._bundle(self.project, args, events.append)
        self.assertEqual(prepare.call_args.args[3], media)
        self.assertTrue(any(event['type'] == 'checks' and event['checks'][0]['status'] == 'ready'
                            for event in events))

    def test_output_file_requires_input_without_overwriting_it(self):
        output = self.root / 'keep.txt'
        output.write_text('keep')
        events = self.execute(output=str(output))
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'bundle_output_invalid')
        self.assertEqual(output.read_text(), 'keep')

    def test_package_certificate_failure_requests_trust_instead_of_more_sources(self):
        from scripts.launcher.installation_dependencies import PackageCommandError
        failure = PackageCommandError(subprocess.CompletedProcess([], 1, '',
            'SSLCertVerificationError private-proxy-path-withheld'))
        events = []
        with patch.object(operations, '_dispatch', side_effect=failure):
            operations.execute({'action': 'bundle'}, events.append, lambda: None, threading.Event())
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'package_tls_failed')
        self.assertIn('CA', error['remedy'])
        self.assertNotIn('withheld', json.dumps(events))

    def test_recovery_failures_keep_specific_safe_diagnostics(self):
        from scripts.build_manager import ManagerBuildError
        from scripts.launcher.installation_dependencies import VirtualEnvironmentRepairError
        for failure in (ManagerBuildError(), ManagerBuildError(dependencies=True),
                        VirtualEnvironmentRepairError(PermissionError(13, 'private-path-withheld'))):
            with self.subTest(code=failure.code):
                events = []
                with patch.object(operations, '_dispatch', side_effect=failure):
                    operations.execute({'action': 'bundle'}, events.append, lambda: None, threading.Event())
                error = next(event for event in events if event['type'] == 'error')
                self.assertEqual(error['code'], failure.code)
                self.assertEqual(error['remedy'], failure.remedy)
                self.assertNotIn('private-path-withheld', json.dumps(events))

    def test_dependency_system_errors_report_category_and_numeric_codes_without_private_data(self):
        cases = (
            (PermissionError(errno.EACCES, 'private-path-withheld'), 5, 'system_access_denied'),
            (OSError(errno.ENOSPC, 'private-path-withheld'), 112, 'system_disk_full'),
            (FileNotFoundError(errno.ENOENT, 'private-path-withheld'), 2, 'system_path_missing'),
            (OSError(errno.ENAMETOOLONG, 'private-path-withheld'), 206, 'system_path_too_long'),
            (OSError(errno.EIO, 'private-path-withheld'), 1117, 'system_io_failed'),
            (UnicodeDecodeError('utf-8', b'private-path-withheld', 0, 1, 'private-path-withheld'),
             None, 'process_output_invalid'),
        )
        for failure, winerror, code in cases:
            failure.winerror = winerror
            def fail(action, args, emit):
                args.progress('Python sanal ortamı doğrulanıyor')
                raise failure
            with self.subTest(code=code), patch.object(operations, '_dispatch', side_effect=fail):
                events = []
                operations.execute({'action': 'ensure'}, events.append, lambda: None, threading.Event())
            error = next(event for event in events if event['type'] == 'error')
            self.assertEqual(error['code'], code)
            self.assertIn('Python sanal ortamı', error['message'])
            if winerror:
                self.assertIn(f'WinError: {winerror}', error['message'])
            self.assertNotIn('Kaynakları test edin', error['remedy'])
            self.assertNotIn('private-path-withheld', json.dumps(events))
            self.assertEqual(events[-1], {'type': 'done', 'ok': False})

    def test_output_inside_any_input_tree_is_relocated_before_claims(self):
        for field in ('source_root', 'manager_distribution', 'assets', 'offline_dir', 'repository'):
            with self.subTest(field=field):
                parent = self.project.root if field == 'source_root' else self.root / field
                parent.mkdir(exist_ok=True)
                marker = parent / 'keep.txt'
                marker.write_text('keep')
                request = {'action': 'bundle', 'output': str(parent), field: str(parent)}
                args = operations.arguments(request)
                args.source_root, args.progress = str(self.project.root), lambda message: None
                with patch('scripts.launcher.installation_profiles.installation_home', return_value=self.home), \
                     patch('scripts.launcher.resource_locks.resource_locks', return_value=nullcontext()) as leases, \
                     patch.object(operations, '_dispatch_claimed'):
                    operations._dispatch('bundle', args, lambda event: None)
                self.assertEqual(args.output.parent, self.home / 'exports')
                self.assertFalse(args.output.exists())
                self.assertTrue(leases.call_args.args[1][path_key(args.output)])
                self.assertEqual(marker.read_text(), 'keep')
