"""Integrity and isolation contracts for desktop-manager source releases."""
from __future__ import annotations

import importlib
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher.model import LauncherError, Project
from scripts.launcher.installation_permissions import require_private, secure_path


class PayloadTests(unittest.TestCase):
    def setUp(self):
        try:
            self.payload = importlib.import_module('scripts.manager.payload')
        except ModuleNotFoundError:
            self.fail('Desktop-manager source payload support is not implemented')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'checkout'
        self.source.mkdir()
        self.project = Project(self.source, self.source / 'backend/manage.py',
                               self.source / 'frontend/package.json', self.source / 'requirements.txt')
        files = {
            'launcher.py': '# launcher\n', 'AWCenter.cmd': '@echo off\n',
            'backend/manage.py': '# manage\n', 'requirements.in': 'django\n',
            'requirements.txt': 'django==5.2\n', 'frontend/package.json': '{}\n',
            'frontend/package-lock.json': '{}\n',
            'scripts/launcher/installation_sources.py': '# pinned sources\n',
            'scripts/launcher/installation_catalog.json': '{}\n',
            'scripts/launcher/installation_python.sha256': 'digest\n',
            'scripts/launcher/installation_python_startup.sha256': 'digest\n',
            'scripts/launcher/installation_verify_python.py': '# verifier\n',
        }
        for relative, value in files.items():
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding='utf-8')

    def prepare(self):
        target = self.root / 'distributed-source'
        self.payload.prepare_source_payload(self.project, target)
        return target

    def test_default_root_is_adjacent_source_when_frozen_and_checkout_when_developing(self):
        with patch.object(self.payload.sys, 'frozen', True, create=True), \
             patch.object(self.payload.sys, 'executable', str(self.root / 'AWCenterManager.exe')):
            self.assertEqual(self.payload.default_source_root(), self.root / 'source')
        with patch.object(self.payload.sys, 'frozen', False, create=True):
            self.assertEqual(self.payload.default_source_root(), Path(__file__).resolve().parents[1])

    def test_safe_payload_excludes_private_unknown_and_generated_files(self):
        for relative in ('unknown.txt', '.env', 'backend/private/customer.txt',
                         'backend/database.sqlite3', 'frontend/node_modules/test.js',
                         'scripts/manager/unknown.py', '.npmrc'):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('must not distribute', encoding='utf-8')
        manager = self.source / 'scripts/manager/payload.py'
        manager.write_text('# approved manager source\n', encoding='utf-8')
        (self.source / 'AWCenterManager.pyw').write_text('# GUI entrypoint\n', encoding='utf-8')
        target = self.prepare()
        self.assertTrue((target / 'scripts/manager/payload.py').is_file())
        self.assertTrue((target / 'AWCenterManager.pyw').is_file())
        for relative in ('unknown.txt', '.env', 'backend/private/customer.txt',
                         'backend/database.sqlite3', 'frontend/node_modules/test.js',
                         'scripts/manager/unknown.py', '.npmrc'):
            self.assertFalse((target / relative).exists(), relative)
        self.payload.verify_source_payload(target)

    def test_extracted_source_keeps_exact_manager_build_inputs_for_automatic_recovery(self):
        files = {'packaging/manager.spec': '# approved freeze specification\n',
                 'packaging/manager-requirements.txt': 'PyInstaller==6.22.3\n',
                 'scripts/build_manager.py': '# approved builder\n'}
        for name, content in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        (self.source / 'packaging/private.txt').write_text('not distributable')
        target = self.prepare()
        for name, content in files.items():
            self.assertTrue((target / name).is_file(), name)
            self.assertEqual((target / name).read_text(encoding='utf-8'), content)
        self.assertFalse((target / 'packaging/private.txt').exists())
        self.payload.verify_source_payload(target)
        regenerated = self.root / 'second-generation'
        extracted = Project(target, target / 'backend/manage.py', target / 'frontend/package.json',
                            target / 'requirements.txt')
        self.payload.prepare_source_payload(extracted, regenerated)
        self.assertEqual(self.payload.verify_source_payload(target)['fingerprint'],
                         self.payload.verify_source_payload(regenerated)['fingerprint'])

    def test_staging_keeps_full_fingerprint_and_reuses_only_verified_identical_release(self):
        source = self.prepare()
        home = self.root / 'home'
        first = self.payload.stage_production_source(source, home)
        manifest = self.payload.verify_source_payload(source)
        self.assertEqual(first, home / 'r' / manifest['fingerprint'][:12])
        self.assertEqual(self.payload.stage_production_source(source, home), first)
        self.assertEqual((first / 'launcher.py').read_bytes(), (source / 'launcher.py').read_bytes())
        self.assertEqual(len(manifest['fingerprint']), 64)
        require_private(first)

    def test_production_package_paths_fit_without_machine_long_path_policy(self):
        from pathlib import PureWindowsPath
        source = self.prepare()
        target = self.payload.stage_production_source(source, self.root / 'home')
        relative = target.relative_to(self.root / 'home')
        windows_home = PureWindowsPath(r'C:\Users\operator-profile-123\AppData\Local\AWCenter')
        header = ('torch-2.13.0.dist-info/licenses/third_party/kineto/libkineto/third_party/'
                  'dynolog/third_party/prometheus-cpp/3rdparty/civetweb/src/third_party/duktape-1.5.2/LICENSE.txt')
        installed = windows_home / relative.as_posix() / '.venv/Lib/site-packages' / header
        self.assertLess(len(str(installed)), 260)
        # Short directory names never replace verification of the full digest.
        self.assertEqual(self.payload.verify_source_payload(target), self.payload.verify_source_payload(source))

    def test_legacy_full_digest_release_remains_readable_and_unchanged(self):
        source = self.prepare()
        home = self.root / 'home'
        staged = self.payload.stage_production_source(source, home)
        fingerprint = self.payload.verify_source_payload(source)['fingerprint']
        legacy = home / 'releases' / fingerprint / 'source'
        if staged != legacy:
            legacy.parent.mkdir(parents=True)
            staged.rename(legacy)
        self.assertEqual(self.payload.resolve_production_source(legacy, home), legacy)
        self.assertEqual(self.payload.stage_production_source(legacy, home), legacy)
        self.assertEqual(self.payload.resolve_production_source(source, home), legacy)

    def test_short_directory_collision_never_replaces_a_different_verified_release(self):
        source = self.prepare()
        home = self.root / 'home'
        first = self.payload.stage_production_source(source, home)
        (self.project.root / 'launcher.py').write_text('# another release\n')
        other = self.root / 'other-release'
        self.payload.prepare_source_payload(self.project, other)
        with patch.object(self.payload, 'production_source_path', return_value=first):
            with self.assertRaises(LauncherError):
                self.payload.stage_production_source(other, home)
        self.assertEqual((first / 'launcher.py').read_bytes(), (source / 'launcher.py').read_bytes())
        self.payload.verify_source_payload(first)

    def test_tampered_existing_release_is_never_overwritten(self):
        source = self.prepare()
        home = self.root / 'home'
        target = self.payload.stage_production_source(source, home)
        (target / 'launcher.py').write_text('tampered\n', encoding='utf-8')
        with self.assertRaises(LauncherError):
            self.payload.stage_production_source(source, home)
        self.assertEqual((target / 'launcher.py').read_text(encoding='utf-8'), 'tampered\n')

    def test_tampered_input_and_unknown_files_are_rejected_before_home_mutation(self):
        for mutation in ('change', 'extra'):
            with self.subTest(mutation=mutation):
                source = self.root / ('source-' + mutation)
                self.payload.prepare_source_payload(self.project, source)
                target = source / ('launcher.py' if mutation == 'change' else 'unknown.py')
                target.write_text('unexpected bytes\n', encoding='utf-8')
                home = self.root / ('home-' + mutation)
                with self.assertRaises(LauncherError):
                    self.payload.stage_production_source(source, home)
                self.assertFalse(home.exists())

    def test_manifest_cannot_authorize_traversal_or_duplicate_windows_paths(self):
        source = self.prepare()
        path = source / self.payload.SOURCE_MANIFEST
        original = json.loads(path.read_text(encoding='utf-8'))
        for bad in ('../outside', 'CON', 'C:/outside', 'backend\\bad.py'):
            with self.subTest(path=bad):
                manifest = {**original, 'artifacts': [{'path': bad, 'size': 0, 'sha256': '0' * 64}]}
                path.write_text(json.dumps(manifest), encoding='utf-8')
                with self.assertRaises(LauncherError):
                    self.payload.verify_source_payload(source)
        original['artifacts'].append({**original['artifacts'][0], 'path': original['artifacts'][0]['path'].upper()})
        path.write_text(json.dumps(original), encoding='utf-8')
        with self.assertRaises(LauncherError):
            self.payload.verify_source_payload(source)

    def test_staged_generated_state_is_ignored_but_unexpected_source_is_rejected(self):
        source = self.prepare()
        home = self.root / 'home'
        target = self.payload.stage_production_source(source, home)
        for relative in ('.venv/generated.py', 'frontend/node_modules/package/test.js',
                         'frontend/dist/index.html', 'backend/staticfiles/site.css',
                         'scripts/__pycache__/launcher.cpython-311.pyc', 'backend/db.sqlite3'):
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('generated', encoding='utf-8')
        self.assertEqual(self.payload.stage_production_source(source, home), target)
        (target / 'backend/unknown.py').write_text('unexpected', encoding='utf-8')
        with self.assertRaises(LauncherError):
            self.payload.stage_production_source(source, home)

    def test_sqlite_rollback_journal_survives_source_verification_after_crash(self):
        source = self.prepare()
        database = source / 'backend/db.sqlite3'
        script = '''import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('CREATE TABLE preserved (value INTEGER)')
connection.execute('INSERT INTO preserved VALUES (0)')
connection.commit()
connection.execute('BEGIN IMMEDIATE')
connection.execute('UPDATE preserved SET value = 1')
os._exit(0)
'''
        subprocess.run([sys.executable, '-c', script, str(database)], check=True, timeout=10)
        journal = database.with_name(database.name + '-journal')
        self.assertTrue(journal.is_file())
        before = journal.read_bytes()
        self.payload.verify_source_payload(source)
        self.assertEqual(journal.read_bytes(), before, 'Verification must leave recovery data to SQLite')
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute('SELECT value FROM preserved').fetchone(), (0,))

    @unittest.skipUnless(hasattr(Path, 'symlink_to'), 'symlinks unavailable')
    def test_input_symlink_and_release_parent_symlink_are_rejected(self):
        source = self.prepare()
        link = source / 'linked.py'
        try:
            link.symlink_to(source / 'launcher.py')
        except OSError:
            self.skipTest('symlink privilege unavailable')
        with self.assertRaises(LauncherError):
            self.payload.verify_source_payload(source)
        link.unlink()
        home = self.root / 'home'
        home.mkdir()
        secure_path(home)
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        (home / 'r').symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises(LauncherError):
            self.payload.stage_production_source(source, home)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_extracted_source_without_manifest_is_not_trusted(self):
        home = self.root / 'home'
        with self.assertRaises(LauncherError):
            self.payload.stage_production_source(self.source, home)
        self.assertFalse(home.exists())

    def test_readonly_resolution_requires_existing_verified_release_without_creating_home(self):
        source = self.prepare()
        home = self.root / 'home'
        with self.assertRaises(LauncherError):
            self.payload.resolve_production_source(source, home)
        self.assertFalse(home.exists())
        target = self.payload.stage_production_source(source, home)
        before = {path.relative_to(home).as_posix(): path.stat().st_mtime_ns
                  for path in home.rglob('*')}
        self.assertEqual(self.payload.resolve_production_source(source, home), target)
        after = {path.relative_to(home).as_posix(): path.stat().st_mtime_ns
                 for path in home.rglob('*')}
        self.assertEqual(before, after)

    def test_canonical_source_can_be_reused_by_stage_and_readonly_resolution(self):
        source = self.prepare()
        home = self.root / 'home'
        target = self.payload.stage_production_source(source, home)
        self.assertEqual(self.payload.stage_production_source(target, home), target)
        self.assertEqual(self.payload.resolve_production_source(target, home), target)
        (target / 'launcher.py').write_text('tampered', encoding='utf-8')
        with self.assertRaises(LauncherError):
            self.payload.resolve_production_source(source, home)
        self.assertEqual((target / 'launcher.py').read_text(encoding='utf-8'), 'tampered')

    def test_copy_rejects_a_different_valid_source_manifest_selected_after_verification(self):
        source = self.prepare()
        selected = self.payload.verify_source_payload(source)
        (source / 'launcher.py').write_text('# changed after selection\n', encoding='utf-8')
        artifacts = self.payload._source_inventory(source)
        changed = {'format_version': 1, 'fingerprint': self.payload._fingerprint(artifacts),
                   'artifacts': artifacts}
        (source / self.payload.SOURCE_MANIFEST).write_text(json.dumps(changed), encoding='utf-8')
        with self.assertRaises(LauncherError):
            self.payload._copy_verified_source(source, self.root / 'copied-source', selected)


if __name__ == '__main__':
    unittest.main()
