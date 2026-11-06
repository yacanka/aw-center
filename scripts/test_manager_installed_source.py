"""Manager actions keep the installed source identity after distribution updates."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.launcher.discovery import discover_project
from scripts.launcher import installation_profiles as profiles
from scripts.manager import operations, payload
from scripts.test_launcher_bundle import project_at


class InstalledSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        environment = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.home = self.root / 'AWCenter'
        self.project = project_at(self.root / 'checkout')
        self.project.package_json.write_text('{"dependencies":{"vue":"3"}}')
        original = self.root / 'original-media'
        payload.prepare_source_payload(self.project, original)
        self.release = payload.stage_production_source(original, self.home)
        certificate, key = self.root / 'certificate.pem', self.root / 'key.pem'
        certificate.write_text('operator certificate fixture')
        key.write_text('operator key fixture')
        profiles.provision_profile(discover_project(self.release), 'prod', self.home,
                                   host='192.0.2.10', tls_cert_file=certificate, tls_key_file=key)
        # The new media is valid but has never been prepared for this profile.
        (self.project.root / 'launcher.py').write_text('# updated distribution\n')
        self.updated = self.root / 'updated-media'
        payload.prepare_source_payload(self.project, self.updated)

    def execute(self, action='doctor', **values):
        events = []
        with patch('scripts.launcher.installation.require_windows'):
            operations.execute({'action': action, 'profile': 'prod', 'source_selection': 'automatic',
                                'source_root': str(self.updated), **values},
                               events.append, lambda: None, threading.Event())
        return events

    def snapshot(self):
        return {str(path.relative_to(self.home)): (path.stat().st_mtime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
                for path in self.home.rglob('*')}

    def test_doctor_checks_recorded_prod_after_media_update_without_writes(self):
        before = self.snapshot()
        events = self.execute()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        checks = next(event['checks'] for event in events if event['type'] == 'checks')
        self.assertEqual(next(row['status'] for row in checks if row['name'] == 'profile'), 'ready')
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn(str(self.release), json.dumps(events))

    def test_start_uses_recorded_prod_after_media_update(self):
        started = []
        def start(project, name, *, on_ready, on_health):
            profile = profiles.load_profile(project, name, self.home)
            started.append(project.root)
            on_ready(profile)
        with patch('scripts.launcher.installation.start_profile', side_effect=start):
            events = self.execute('start')
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(started, [self.release])
        self.assertEqual(next(event['url'] for event in events if event['type'] == 'ready'),
                         'https://192.0.2.10:443/app/')

    def test_explicit_updated_source_is_not_silently_replaced_by_old_profile(self):
        before = self.snapshot()
        events = self.execute(source_selection='explicit')
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'production_source_not_prepared')
        self.assertIn('boş bırakın', error['remedy'])
        self.assertNotIn('ZIP', error['remedy'])
        self.assertNotIn(str(self.updated), json.dumps(events))
        self.assertFalse(any(event['type'] == 'checks' for event in events))
        self.assertEqual(self.snapshot(), before)

    def test_doctor_keeps_legacy_installed_release_after_media_update(self):
        fingerprint = payload.verify_source_payload(self.release)['fingerprint']
        legacy = self.home / 'releases' / fingerprint / 'source'
        legacy.parent.mkdir(parents=True)
        self.release.rename(legacy)
        path = self.home / 'config/prod.profile.json'
        profile = json.loads(path.read_text())
        profile['source_root'] = str(legacy)
        path.write_text(json.dumps(profile))
        before = self.snapshot()
        events = self.execute()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        checks = next(event['checks'] for event in events if event['type'] == 'checks')
        self.assertEqual(next(row['status'] for row in checks if row['name'] == 'profile'), 'ready')
        self.assertEqual(self.snapshot(), before)

    def test_invalid_profile_is_not_bypassed_by_valid_distribution(self):
        path = self.home / 'config/prod.profile.json'
        path.write_text('{"invalid":"private-value"}')
        before = self.snapshot()
        events = self.execute()
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        self.assertFalse(any(event['type'] == 'checks' for event in events))
        self.assertNotIn('private-value', json.dumps(events))
        self.assertEqual(self.snapshot(), before)

    def test_tampered_installed_release_is_not_hidden_by_valid_new_media(self):
        (self.release / 'launcher.py').write_text('# tampered installed source\n')
        before = self.snapshot()
        events = self.execute()
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
        self.assertEqual(next(event['code'] for event in events if event['type'] == 'error'), 'integrity_failed')
        self.assertEqual(self.snapshot(), before)
