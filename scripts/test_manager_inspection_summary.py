"""Window inspection reports metadata without executing installed application code."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from scripts import test_manager_ensure as fixtures
from scripts.launcher import installation_profiles as profiles
from scripts.launcher.installation_permissions import secure_path
from scripts.launcher.installation_state import private_directory
from scripts.launcher_test_support import create_project
from scripts.manager import inspection, operations


class InspectionSummaryTests(unittest.TestCase):
    setUp = fixtures.EnsureTests.setUp

    def prepared(self):
        profile = profiles.provision_profile(self.project, 'dev', self.home)
        self.project.python.parent.mkdir(parents=True)
        self.project.python.write_bytes(b'not executed by window inspection')
        return profile

    def inspect(self, **values):
        events = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(inspection, 'installation_home', return_value=self.home))
            stack.enter_context(patch.object(inspection, 'require_windows'))
            # These paths may read/execute thousands of installed files. A
            # window summary must remain usable when none is available.
            for target in (
                'scripts.manager.operations._project_for',
                'scripts.launcher.installation.inspect_toolchain',
                'scripts.launcher.installation._core_checks',
                'scripts.launcher.discovery.discover_project',
                'scripts.launcher.runtime_selection.tool_choices',
                'scripts.launcher.installation.backend_inspection',
                'scripts.launcher.installation.provision',
                'scripts.launcher.installation_dependencies._package_inventory',
                'scripts.launcher.installation_features.inspect_features',
                'scripts.manager.payload.verify_source_payload',
            ):
                stack.enter_context(patch(target, side_effect=AssertionError('expensive inspection used')))
            operations.execute({'action': 'inspect', 'source_root': str(self.project.root),
                                'source_selection': 'automatic', **values},
                               events.append, lambda: None, threading.Event())
        return events

    def test_recorded_profile_is_unverified_without_expensive_checks(self):
        profile = self.prepared()
        before = Path(profile['env_file']).read_bytes()
        events = self.inspect(source_root=str(self.root / 'updated-media'))
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        summary = next(event for event in events if event['type'] == 'profile')
        self.assertEqual(summary['status'], 'unverified')
        self.assertNotIn('checks', summary)
        self.assertIn('açılırken', summary['detail'])
        self.assertNotIn(str(self.project.root), json.dumps(events))
        self.assertNotIn(profiles.read_profile_environment(profile)['SECRET_KEY'], json.dumps(events))
        self.assertEqual(Path(profile['env_file']).read_bytes(), before)

    def test_new_profile_summary_does_not_discover_tools_or_create_storage(self):
        events = self.inspect()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(next(event['status'] for event in events if event['type'] == 'profile'),
                         'not_installed')
        self.assertFalse(self.home.exists())

    def test_missing_python_reports_incomplete_without_running_it(self):
        self.prepared()
        self.project.python.unlink()
        events = self.inspect()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(next(event['status'] for event in events if event['type'] == 'profile'),
                         'incomplete')

    def test_missing_source_reports_incomplete_without_discovery(self):
        self.prepared()
        self.project.manage_py.unlink()
        events = self.inspect()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(next(event['status'] for event in events if event['type'] == 'profile'),
                         'incomplete')

    def test_pending_profile_is_not_reported_as_ready(self):
        self.prepared()
        pending = self.home / 'config/dev.pending.json'
        pending.write_text('{}', encoding='utf-8')
        secure_path(pending)
        events = self.inspect()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(next(event['status'] for event in events if event['type'] == 'profile'),
                         'incomplete')

    def test_pending_first_installation_remains_incomplete_without_recovery(self):
        config = private_directory(self.home / 'config', root=self.home)
        pending = config / 'dev.pending.json'
        pending.write_text('{}', encoding='utf-8')
        secure_path(pending)
        events = self.inspect()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(next(event['status'] for event in events if event['type'] == 'profile'),
                         'incomplete')
        self.assertEqual(pending.read_text(encoding='utf-8'), '{}')
        self.assertFalse((config / 'dev.profile.json').exists())

    def test_recorded_production_summary_does_not_require_source_manifest(self):
        source = private_directory(self.home / 'r' / ('a' * 12), root=self.home)
        project = create_project(source)
        certificate, key = self.root / 'certificate.pem', self.root / 'key.pem'
        certificate.write_text('certificate fixture', encoding='utf-8')
        key.write_text('private key fixture', encoding='utf-8')
        profiles.provision_profile(project, 'prod', self.home, host='192.0.2.10',
                                   tls_cert_file=certificate, tls_key_file=key)
        project.python.parent.mkdir(parents=True)
        project.python.write_bytes(b'not executed')
        events = self.inspect(profile='prod')
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(next(event['status'] for event in events if event['type'] == 'profile'),
                         'unverified')
        self.assertNotIn(str(source), json.dumps(events))
        self.assertFalse((source / 'manager-source-manifest.json').exists())

    def test_orphan_environment_is_reported_without_reading_secrets(self):
        profile = self.prepared()
        (self.home / 'config/dev.profile.json').unlink()
        events = self.inspect()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(next(event['status'] for event in events if event['type'] == 'profile'),
                         'blocked')
        self.assertNotIn(profiles.read_profile_environment(profile)['SECRET_KEY'], json.dumps(events))

    def test_missing_environment_keeps_existing_validation_and_does_not_recreate_it(self):
        profile = self.prepared()
        env = Path(profile['env_file'])
        env.unlink()
        events = self.inspect()
        self.assertEqual(events[-1], {'type': 'done', 'ok': False}, events)
        self.assertFalse(any(event['type'] == 'profile' for event in events))
        self.assertFalse(env.exists())
        self.assertNotIn(str(env), json.dumps(events))

    def test_explicit_different_source_cannot_bypass_profile_identity(self):
        self.prepared()
        events = self.inspect(source_selection='explicit', source_root=str(self.root / 'other-source'))
        self.assertEqual(events[-1], {'type': 'done', 'ok': False}, events)
        self.assertFalse(any(event['type'] == 'profile' for event in events))

    @unittest.skipIf(os.name == 'nt', 'POSIX ownership fixture; native ACLs have separate coverage')
    def test_summary_rejects_public_profile_permissions(self):
        self.prepared()
        path = self.home / 'config/dev.profile.json'
        path.chmod(0o644)
        events = self.inspect()
        self.assertEqual(events[-1], {'type': 'done', 'ok': False}, events)
        self.assertFalse(any(event['type'] == 'profile' for event in events))
