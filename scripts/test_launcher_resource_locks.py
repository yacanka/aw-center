"""OS resource claims protect live profiles across independent processes."""
import importlib
import errno
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.launcher.model import LauncherError


class ResourceLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / 'home'
        try:
            self.locks = importlib.import_module('scripts.launcher.resource_locks')
        except ModuleNotFoundError:
            self.fail('Cross-process lifecycle leases are missing')

    def child(self, resource, write):
        program = '''import sys
from pathlib import Path
from scripts.launcher.resource_locks import resource_locks
from scripts.launcher.model import LauncherError
try:
    with resource_locks(Path(sys.argv[1]), {sys.argv[2]: sys.argv[3] == '1'}):
        pass
except LauncherError:
    sys.exit(3)
'''
        return subprocess.run([sys.executable, '-B', '-c', program, str(self.home), resource, str(int(write))],
                              capture_output=True, timeout=10).returncode

    def test_reader_allows_reader_but_rejects_writer(self):
        with self.locks.resource_locks(self.home, {'runtime': False}):
            self.assertEqual(self.child('runtime', False), 0)
            self.assertEqual(self.child('runtime', True), 3)
        self.assertEqual(self.child('runtime', True), 0)

    def test_writer_downgrades_without_releasing_profile_ownership(self):
        with self.locks.resource_locks(self.home, {'profile:dev': True, 'runtime': True}):
            self.assertEqual(self.child('runtime', False), 3)
            self.locks.downgrade_runtime_claims()
            self.assertEqual(self.child('runtime', False), 0)
            self.assertEqual(self.child('runtime', True), 3)
            self.assertEqual(self.child('profile:dev', True), 3)

    def test_failed_multi_claim_acquisition_releases_earlier_locks(self):
        with self.locks.resource_locks(self.home, {'z': True}):
            code = '''from pathlib import Path
import sys
from scripts.launcher.resource_locks import resource_locks
from scripts.launcher.model import LauncherError
try:
    with resource_locks(Path(sys.argv[1]), {'a': True, 'z': True}): pass
except LauncherError: pass
'''
            result = subprocess.run([sys.executable, '-B', '-c', code, str(self.home)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(self.child('a', True), 0)

    def test_parent_path_write_conflicts_with_nested_output(self):
        parent = self.home.parent / 'output'
        claims = self.locks.path_claims(parent / 'nested', write=True)
        with self.locks.resource_locks(self.home, claims):
            key = self.locks.path_key(parent)
            self.assertEqual(self.child(key, True), 3)

    def test_nested_launcher_calls_reuse_their_existing_claims(self):
        with self.locks.resource_locks(self.home, {'profile:dev': True}):
            with self.locks.resource_locks(self.home, {'profile:dev': True}):
                self.assertEqual(self.child('profile:dev', True), 3)

    def test_lock_file_access_denied_is_not_reported_as_contention(self):
        error = PermissionError(errno.EACCES, 'private-path-withheld')
        error.winerror = 5
        with patch.object(Path, 'open', side_effect=error):
            with self.assertRaises(LauncherError) as caught:
                with self.locks.resource_locks(self.home, {'runtime': True}):
                    self.fail('Denied lock file was accepted')
        self.assertEqual(getattr(caught.exception, 'code', None), 'storage_lock_failed')
        self.assertIn('WinError: 5', str(caught.exception))
        self.assertNotIn('private-path-withheld', str(caught.exception))

    def test_windows_lock_violation_is_reported_as_contention(self):
        error = OSError(errno.EACCES, 'private-path-withheld')
        error.winerror = 33
        with patch.object(self.locks._Lease, '_lock', side_effect=error):
            with self.assertRaises(LauncherError) as caught:
                with self.locks.resource_locks(self.home, {'runtime': True}):
                    self.fail('Competing lock was accepted')
        self.assertEqual(getattr(caught.exception, 'code', None), 'resource_busy')
        self.assertIn('WinError: 33', str(caught.exception))

    def test_windows_lock_access_denied_is_not_reported_as_contention(self):
        error = PermissionError(errno.EACCES, 'private-path-withheld')
        error.winerror = 5
        with patch.object(self.locks._Lease, '_lock', side_effect=error):
            with self.assertRaises(LauncherError) as caught:
                with self.locks.resource_locks(self.home, {'runtime': True}):
                    self.fail('Denied lock was accepted')
        self.assertEqual(getattr(caught.exception, 'code', None), 'storage_lock_failed')

    def test_lock_directory_io_failure_keeps_safe_numeric_diagnostics(self):
        error = OSError(errno.ENOSPC, 'private-path-withheld')
        with patch.object(self.locks, 'private_directory', side_effect=error):
            with self.assertRaises((LauncherError, OSError)) as caught:
                with self.locks.resource_locks(self.home, {'runtime': True}):
                    self.fail('Unavailable directory was accepted')
        self.assertEqual(getattr(caught.exception, 'code', None), 'storage_lock_failed')
        self.assertIn(f'errno: {errno.ENOSPC}', str(caught.exception))
        self.assertNotIn('private-path-withheld', str(caught.exception))
