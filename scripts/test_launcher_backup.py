"""Real disposable SQLite tests for Manager migration snapshots."""
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from scripts.launcher.model import LauncherError
from scripts.launcher.installation_permissions import secure_path
from scripts.launcher.installation_probe import inspect_sqlite


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        migration = self.source / 'backend' / 'sample' / 'migrations'
        migration.mkdir(parents=True)
        (migration / '0001_initial.py').write_text('# initial')
        self.home = self.root / 'home'
        self.home.mkdir()
        secure_path(self.home)
        self.db = self.home / 'db.sqlite3'
        with sqlite3.connect(self.db) as connection:
            connection.execute('CREATE TABLE django_migrations (app TEXT, name TEXT)')
            connection.execute("INSERT INTO django_migrations VALUES ('sample', '0001_initial')")
        secure_path(self.db)
        self.media = self.home / 'private_media'
        self.media.mkdir()
        secure_path(self.media)
        (self.media / 'artifact').write_bytes(b'private artifact')
        secure_path(self.media / 'artifact')
        self.env = self.home / 'dev.env'
        self.env.write_text(f'DATABASE_URL=sqlite:///{self.db}\nPRIVATE_MEDIA_ROOT={self.media}\nSECRET_KEY=secret-never-manifest\n')
        secure_path(self.env)
        self.profile = {'name': 'dev', 'installation_home': str(self.home), 'env_file': str(self.env), 'source_root': str(self.source)}
        self.project = SimpleNamespace(root=self.source)
        self.required = {('sample', '0001_initial'), ('sample', '0002_next')}

    def run_migration(self, migrate=None, **kwargs):
        from scripts.launcher.installation_backup import run_backed_up_migrations
        def apply():
            with sqlite3.connect(self.db) as connection:
                connection.execute("INSERT INTO django_migrations VALUES ('sample', '0002_next')")
        return run_backed_up_migrations(self.project, self.profile,
            lambda: inspect_sqlite(self.db, self.required), migrate or apply,
            lambda: None, **kwargs)

    def test_verified_backup_precedes_migration(self):
        receipt = self.run_migration()
        self.assertEqual(receipt['status'], 'verified')
        directory = Path(receipt['backup_directory'])
        with sqlite3.connect(directory / 'database.sqlite3') as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM django_migrations').fetchone()[0], 1)
        self.assertEqual((directory / 'private_media' / 'artifact').read_bytes(), b'private artifact')
        self.assertNotIn('secret-never-manifest', (directory / 'manifest.json').read_text())

    def test_unknown_existing_database_rejected(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("INSERT INTO django_migrations VALUES ('legacy', '0001_old')")
        with self.assertRaises(LauncherError):
            self.run_migration()

    def test_unrecognized_nonempty_database_rejected(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute('DROP TABLE django_migrations')
        with self.assertRaises(LauncherError):
            self.run_migration()

    def test_failed_migration_never_automatically_repeats(self):
        def fail():
            raise RuntimeError('private vendor detail')
        with self.assertRaises(LauncherError):
            self.run_migration(fail)
        with self.assertRaises(LauncherError):
            self.run_migration()
        receipts = list((self.home / 'backups' / 'dev').glob('*/receipt.json'))
        self.assertEqual(len(receipts), 1)
        self.assertNotIn('private vendor detail', receipts[0].read_text())

    def test_cancelled_snapshot_does_not_migrate(self):
        with self.assertRaises(LauncherError):
            self.run_migration(cancelled=lambda: True)
        self.assertEqual(inspect_sqlite(self.db, self.required)['schema'], 'pending')

    def test_existing_wal_rejected(self):
        Path(str(self.db) + '-wal').touch()
        with self.assertRaises(LauncherError):
            self.run_migration()

    def test_probe_marks_known_pending_and_unknown_schema(self):
        state = inspect_sqlite(self.db, self.required)
        self.assertTrue(state.get('auto_migrate_safe'))
        self.assertEqual(state['migration_plan']['pending'], [['sample', '0002_next']])
        with sqlite3.connect(self.db) as connection:
            connection.execute("INSERT INTO django_migrations VALUES ('legacy', 'old')")
        self.assertFalse(inspect_sqlite(self.db, self.required)['auto_migrate_safe'])

    def test_concurrent_writer_blocks_snapshot(self):
        with sqlite3.connect(self.db) as writer:
            writer.execute('BEGIN IMMEDIATE')
            with self.assertRaises(LauncherError):
                self.run_migration()

    def test_media_changes_abort_before_migration(self):
        from unittest.mock import patch
        from scripts.launcher import installation_backup
        original = installation_backup._copy_media
        def changing_copy(*args):
            original(*args)
            (self.media / 'artifact').write_bytes(b'changed concurrently')
        with patch.object(installation_backup, '_copy_media', side_effect=changing_copy):
            with self.assertRaises(LauncherError):
                self.run_migration()
        self.assertEqual(inspect_sqlite(self.db, self.required)['schema'], 'pending')

    def test_completed_interrupted_migration_finishes_postcheck_without_repeat(self):
        def applied_then_crashed():
            with sqlite3.connect(self.db) as connection:
                connection.execute("INSERT INTO django_migrations VALUES ('sample', '0002_next')")
            raise RuntimeError('process lost')
        with self.assertRaises(LauncherError):
            self.run_migration(applied_then_crashed)
        receipt = self.run_migration(lambda: self.fail('migration repeated'))
        self.assertEqual(receipt['status'], 'verified')
        stored = json.loads(next((self.home / 'backups' / 'dev').glob('*/receipt.json')).read_text())
        self.assertEqual(stored['status'], 'verified')

    def test_interrupted_snapshot_tamper_blocks_completion(self):
        def applied_then_crashed():
            with sqlite3.connect(self.db) as connection:
                connection.execute("INSERT INTO django_migrations VALUES ('sample', '0002_next')")
            raise RuntimeError('process lost')
        with self.assertRaises(LauncherError):
            self.run_migration(applied_then_crashed)
        backup = next((self.home / 'backups' / 'dev').glob('*/database.sqlite3'))
        backup.write_bytes(b'corrupt')
        with self.assertRaises(LauncherError):
            self.run_migration()

    def test_empty_database_initialization_needs_no_snapshot(self):
        self.db.unlink()
        def initialize():
            with sqlite3.connect(self.db) as connection:
                connection.execute('CREATE TABLE django_migrations (app TEXT, name TEXT)')
                connection.executemany('INSERT INTO django_migrations VALUES (?, ?)', sorted(self.required))
        receipt = self.run_migration(initialize)
        self.assertTrue(receipt['initialized'])
        self.assertFalse(list((self.home / 'backups' / 'dev').glob('*/database.sqlite3')))

    def test_interrupted_initialization_never_automatically_repeats(self):
        self.db.unlink()
        def partial_initialize():
            with sqlite3.connect(self.db) as connection:
                connection.execute('CREATE TABLE django_migrations (app TEXT, name TEXT)')
                connection.execute("INSERT INTO django_migrations VALUES ('sample', '0001_initial')")
            raise RuntimeError('stopped')
        with self.assertRaises(LauncherError):
            self.run_migration(partial_initialize)
        with self.assertRaises(LauncherError):
            self.run_migration()

    def test_snapshot_preserves_empty_private_directories(self):
        (self.media / 'empty').mkdir()
        secure_path(self.media / 'empty')
        receipt = self.run_migration()
        self.assertTrue((Path(receipt['backup_directory']) / 'private_media' / 'empty').is_dir())

    def test_completed_initialization_can_finish_postcheck_after_crash(self):
        self.db.unlink()
        def initialize_then_crash():
            with sqlite3.connect(self.db) as connection:
                connection.execute('CREATE TABLE django_migrations (app TEXT, name TEXT)')
                connection.executemany('INSERT INTO django_migrations VALUES (?, ?)', sorted(self.required))
            raise RuntimeError('stopped')
        with self.assertRaises(LauncherError):
            self.run_migration(initialize_then_crash)
        self.assertEqual(self.run_migration(lambda: self.fail('repeated'))['status'], 'verified')

    def test_symlinked_artifact_never_copied(self):
        (self.media / 'link').symlink_to(self.env)
        with self.assertRaises(LauncherError):
            self.run_migration()
        self.assertEqual(inspect_sqlite(self.db, self.required)['schema'], 'pending')

    def test_changed_migration_source_prevents_interrupted_completion(self):
        def applied_then_crashed():
            with sqlite3.connect(self.db) as connection:
                connection.execute("INSERT INTO django_migrations VALUES ('sample', '0002_next')")
            raise RuntimeError('process lost')
        with self.assertRaises(LauncherError):
            self.run_migration(applied_then_crashed)
        (self.source / 'backend/sample/migrations/0001_initial.py').write_text('# changed')
        with self.assertRaises(LauncherError):
            self.run_migration()

    def test_snapshot_timeout_never_migrates(self):
        with self.assertRaises(LauncherError):
            self.run_migration(timeout=0)
        self.assertEqual(inspect_sqlite(self.db, self.required)['schema'], 'pending')

    def test_unresolved_receipt_query_is_read_only_and_tracks_failure(self):
        from scripts.launcher.installation_backup import has_unresolved_migration
        self.assertFalse(has_unresolved_migration(self.profile))
        self.assertFalse((self.home / 'backups').exists())
        def fail():
            raise RuntimeError('stopped')
        with self.assertRaises(LauncherError):
            self.run_migration(fail)
        self.assertTrue(has_unresolved_migration(self.profile))

    def test_malformed_receipt_is_safely_rejected(self):
        def fail():
            raise RuntimeError('stopped')
        with self.assertRaises(LauncherError):
            self.run_migration(fail)
        receipt = next((self.home / 'backups/dev').glob('*/receipt.json'))
        receipt.write_text('{}')
        with self.assertRaises(LauncherError):
            self.run_migration()

    def test_real_backend_probe_binds_installed_migration_sources(self):
        import os
        import subprocess
        import sys
        environment = os.environ.copy()
        environment.update(AWCENTER_ENV_FILE=os.devnull, SECRET_KEY='isolated-probe-fixture',
                           DEBUG='True', DATABASE_URL='sqlite:///' + str(self.home / 'absent.sqlite3'),
                           PRIVATE_MEDIA_ROOT=str(self.media), PYTHONDONTWRITEBYTECODE='1')
        completed = subprocess.run([sys.executable, '-m', 'scripts.launcher.installation_probe', 'inspect'],
                                   cwd=Path(__file__).resolve().parents[1], env=environment,
                                   capture_output=True, text=True, check=True)
        state = json.loads(completed.stdout)
        self.assertEqual(len(state['migration_plan'].get('source_sha256', '')), 64)

    def test_confirmation_after_snapshot_can_decline_without_blocking_retry(self):
        from scripts.launcher.installation_backup import has_unresolved_migration
        def decline():
            directory = next((self.home / 'backups/dev').iterdir())
            self.assertTrue((directory / 'manifest.json').is_file())
            self.assertFalse(has_unresolved_migration(self.profile))
            raise InterruptedError('declined')
        with self.assertRaises(InterruptedError):
            self.run_migration(before_migrate=decline)
        self.assertFalse(has_unresolved_migration(self.profile))
        self.assertEqual(inspect_sqlite(self.db, self.required)['schema'], 'pending')
        self.assertEqual(self.run_migration()['status'], 'verified')

    def test_ready_database_with_unknown_migrations_is_rejected(self):
        with sqlite3.connect(self.db) as connection:
            connection.executemany('INSERT INTO django_migrations VALUES (?, ?)',
                                   [('sample', '0002_next'), ('legacy', '0001_old')])
        state = inspect_sqlite(self.db, self.required)
        self.assertEqual(state['schema'], 'ready')
        self.assertFalse(state['auto_migrate_safe'])
        with self.assertRaises(LauncherError):
            self.run_migration(lambda: self.fail('unexpected migration'))

    def test_media_cannot_enclose_backup_namespace(self):
        self.env.write_text(f'DATABASE_URL=sqlite:///{self.db}\nPRIVATE_MEDIA_ROOT={self.home / "backups"}\n')
        with self.assertRaises(LauncherError):
            self.run_migration()
        self.assertFalse((self.home / 'backups').exists())

    def test_media_cannot_enclose_private_environment(self):
        old_env = self.env
        self.env = self.media / 'private.env'
        self.env.write_bytes(old_env.read_bytes())
        secure_path(self.env)
        self.profile['env_file'] = str(self.env)
        with self.assertRaises(LauncherError):
            self.run_migration()
        self.assertFalse((self.home / 'backups').exists())

    def test_cancellation_exception_during_snapshot_preserves_type(self):
        from scripts.launcher.process import OperationCancelled
        checks = 0
        def cancel_mid_snapshot():
            nonlocal checks
            checks += 1
            if checks > 7:
                raise OperationCancelled('stopped')
            return False
        with self.assertRaises(OperationCancelled):
            self.run_migration(cancelled=cancel_mid_snapshot)
        self.assertEqual(inspect_sqlite(self.db, self.required)['schema'], 'pending')

    def test_windows_publication_requires_write_through_and_reports_failure(self):
        from unittest.mock import Mock, patch
        from scripts.launcher import installation_backup
        native = Mock()
        native.MoveFileExW.return_value = 1
        with patch('ctypes.WinDLL', return_value=native, create=True):
            installation_backup._windows_publish(self.env, self.home / 'target', replace=True)
        self.assertEqual(native.MoveFileExW.call_args.args[2], 0x9)
        native.MoveFileExW.return_value = 0
        with patch('ctypes.WinDLL', return_value=native, create=True):
            with self.assertRaises(LauncherError):
                installation_backup._windows_publish(self.env, self.home / 'target', replace=False)

    def test_durability_failure_prevents_migration(self):
        from unittest.mock import patch
        from scripts.launcher import installation_backup
        original = installation_backup._flush_snapshot
        def fail_flush(*args):
            original(*args)
            raise LauncherError('directory publication unavailable')
        with patch.object(installation_backup, '_flush_snapshot', side_effect=fail_flush):
            with self.assertRaises(LauncherError):
                self.run_migration(lambda: self.fail('migration ran before durable publication'))
        self.assertEqual(inspect_sqlite(self.db, self.required)['schema'], 'pending')

    def test_posix_parent_and_nested_media_are_synced_before_migration(self):
        import os
        if os.name == 'nt':
            self.skipTest('POSIX fsync contract')
        from unittest.mock import patch
        from scripts.launcher import installation_backup
        nested = self.media / 'nested'
        nested.mkdir()
        secure_path(nested)
        (nested / 'item').write_bytes(b'nested artifact')
        secure_path(nested / 'item')
        synchronized = []
        original = installation_backup._sync_directory
        def sync(path):
            original(path)
            synchronized.append(Path(path))
        def migrate():
            directory = next((self.home / 'backups/dev').iterdir())
            self.assertIn(directory.parent, synchronized)
            self.assertIn(directory / 'private_media/nested', synchronized)
            with sqlite3.connect(self.db) as connection:
                connection.execute("INSERT INTO django_migrations VALUES ('sample', '0002_next')")
        with patch.object(installation_backup, '_sync_directory', side_effect=sync):
            self.run_migration(migrate)

    def test_migration_result_with_unknown_history_never_verified(self):
        def unexpected_history():
            with sqlite3.connect(self.db) as connection:
                connection.executemany('INSERT INTO django_migrations VALUES (?, ?)',
                                       [('sample', '0002_next'), ('legacy', 'old')])
        with self.assertRaises(LauncherError):
            self.run_migration(unexpected_history)
        receipt = json.loads(next((self.home / 'backups/dev').glob('*/receipt.json')).read_text())
        self.assertEqual(receipt['status'], 'failed')
