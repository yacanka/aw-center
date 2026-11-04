"""Only non-secret desktop inputs survive a Manager restart."""
import importlib
import errno
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher.installation_permissions import secure_path
from scripts.launcher.model import LauncherError


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.preferences = importlib.import_module('scripts.manager.preferences')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve() / 'AWCenterManager'

    def test_restart_restores_inputs_without_credentials_or_migration_consent(self):
        values = {'profile': 'prod', 'source_mode': 'corporate', 'source_root': 'C:/AW/source',
                  'python_command': 'C:/Python 311/python.exe', 'env_file': 'C:/config/prod.env',
                  'host': '192.0.2.1', 'backend_port': '8443', 'tls_key_file': 'C:/tls/private.key',
                  'python_index_url': 'https://packages.example/simple', 'install_python': False,
                  'migrate': True, 'password': 'must-not-persist', 'username': 'must-not-persist'}
        self.preferences.save_preferences(self.home, values)
        restored = self.preferences.load_preferences(self.home)
        for key in ('profile', 'source_mode', 'source_root', 'python_command', 'env_file',
                    'host', 'backend_port', 'tls_key_file', 'python_index_url', 'install_python'):
            self.assertEqual(restored[key], values[key])
        self.assertFalse(restored.get('migrate', False))
        raw = (self.home / 'manager.json').read_text(encoding='utf-8')
        self.assertNotIn('must-not-persist', raw)

    def test_credential_urls_are_not_persisted_even_in_disabled_fields(self):
        self.preferences.save_preferences(self.home, {'source_mode': 'offline',
            'python_index_url': 'https://user:private@packages.example/simple',
            'npm_registry_url': 'https://npm.example?token=private',
            'repository': 'https://packages.example/#private'})
        raw = (self.home / 'manager.json').read_text(encoding='utf-8')
        self.assertNotIn('private', raw)
        self.assertEqual(self.preferences.load_preferences(self.home)['source_mode'], 'offline')

    def test_empty_and_corrupted_preferences_do_not_provision_application_state(self):
        self.assertEqual(self.preferences.load_preferences(self.home), {})
        self.assertFalse(self.home.exists())
        self.preferences.save_preferences(self.home, {'profile': 'dev'})
        path = self.home / 'manager.json'
        for content in ('broken-json', json.dumps({'version': 99, 'values': {}}),
                        'x' * (128 * 1024 + 1), '[' * 2000 + ']' * 2000):
            path.write_text(content, encoding='utf-8')
            with self.assertRaises(LauncherError):
                self.preferences.load_preferences(self.home)

    def test_symlink_destination_cannot_overwrite_another_file(self):
        self.preferences.save_preferences(self.home, {'profile': 'dev'})
        target = self.home / 'untouched'
        target.write_text('original', encoding='utf-8')
        secure_path(target)
        path = self.home / 'manager.json'
        path.unlink()
        try:
            path.symlink_to(target)
        except OSError:
            self.skipTest('Symlinks are unavailable to the current Windows user')
        with self.assertRaises(LauncherError):
            self.preferences.save_preferences(self.home, {'profile': 'prod'})
        self.assertEqual(target.read_text(encoding='utf-8'), 'original')

    def test_existing_installation_permissions_do_not_block_preferences(self):
        installation = self.home.parent / 'AWCenter'
        installation.mkdir()
        sentinel = installation / 'keep.txt'
        sentinel.write_text('keep existing installation', encoding='utf-8')
        if os.name != 'nt':
            installation.chmod(0o500)
            self.addCleanup(installation.chmod, 0o700)
        before = installation.stat().st_mode
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.home.parent)}):
            home = self.preferences.preferences_home()
            self.preferences.save_preferences(home, {'python_command': 'python'})
            self.assertEqual(self.preferences.load_preferences(home)['python_command'], 'python')
        self.assertEqual(installation.stat().st_mode, before)
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'keep existing installation')
        self.assertFalse((installation / 'config').exists())

    def test_private_legacy_inputs_are_migrated_without_changing_old_file(self):
        legacy = self.home.parent / 'AWCenter/config/manager.json'
        legacy.parent.mkdir(parents=True)
        secure_path(legacy.parent.parent)
        secure_path(legacy.parent)
        original = json.dumps({'version': 1, 'values': {'python_command': 'python', 'migrate': True}}).encode()
        legacy.write_bytes(original)
        secure_path(legacy)
        restored = self.preferences.load_preferences(self.home)
        self.assertEqual(restored['python_command'], 'python')
        self.assertFalse(restored.get('migrate', False))
        self.preferences.save_preferences(self.home, {**restored, 'python_command': 'py -3.11'})
        self.assertEqual(self.preferences.load_preferences(self.home)['python_command'], 'py -3.11')
        self.assertEqual(legacy.read_bytes(), original)

    def test_failed_replace_keeps_saved_values_and_reports_safe_details(self):
        self.preferences.save_preferences(self.home, {'python_command': 'python'})
        original = (self.home / 'manager.json').read_bytes()
        for number, winerror, code in ((errno.ENOSPC, 112, 'disk_full'),
                                       (errno.EACCES, 32, 'file_locked'),
                                       (errno.EACCES, 5, 'access_denied')):
            error = OSError(number, 'private-payload C:/private/user token=hidden')
            error.winerror = winerror
            with self.subTest(code=code), patch.object(self.preferences.os, 'replace', side_effect=error):
                with self.assertRaises(self.preferences.PreferencesError) as caught:
                    self.preferences.save_preferences(self.home, {'python_command': 'changed'})
            self.assertEqual(caught.exception.stage, 'replace')
            self.assertEqual(caught.exception.code, code)
            message = caught.exception.message('save')
            self.assertIn(f'WinError {winerror}', message)
            self.assertIn('%LOCALAPPDATA%\\AWCenterManager\\manager.json', message)
            self.assertIn('Atomik', message)
            self.assertNotIn('private-payload', message)
            self.assertNotIn('C:/private/user', message)
            self.assertNotIn('hidden', message)
            self.assertEqual((self.home / 'manager.json').read_bytes(), original)
            self.assertEqual(list(self.home.glob('.manager-*')), [])

    def test_untrusted_legacy_file_is_not_imported(self):
        legacy = self.home.parent / 'AWCenter/config/manager.json'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{}', encoding='utf-8')
        with patch.object(self.preferences, 'require_private', side_effect=LauncherError('private details')):
            with self.assertRaises(self.preferences.PreferencesError) as caught:
                self.preferences.load_preferences(self.home)
        self.assertTrue(caught.exception.legacy)
        self.assertEqual(caught.exception.stage, 'permissions')
        self.assertNotIn('private details', caught.exception.message('load'))
        self.preferences.save_preferences(self.home, {'python_command': 'python'})
        self.assertEqual(self.preferences.load_preferences(self.home)['python_command'], 'python')

    def test_invalid_user_location_has_actionable_diagnostics(self):
        for local in ('', 'relative/location', '/invalid\nlocation'):
            with self.subTest(local=local), patch.dict(os.environ, {'LOCALAPPDATA': local}):
                with self.assertRaises(self.preferences.PreferencesError) as caught:
                    self.preferences.preferences_home()
            self.assertEqual(caught.exception.stage, 'location')
            self.assertEqual(caught.exception.code, 'localappdata')

    def test_acl_failure_message_keeps_check_name_and_numeric_error(self):
        from scripts.launcher.installation_permissions import PermissionCheckError
        self.preferences.save_preferences(self.home, {'python_command': 'python'})
        with patch.object(self.preferences, 'require_private', side_effect=PermissionCheckError('acl_read', winerror=5)):
            with self.assertRaises(self.preferences.PreferencesError) as caught:
                self.preferences.load_preferences(self.home)
        message = caught.exception.message('load')
        self.assertIn('acl_read', message)
        self.assertIn('WinError 5', message)
        self.assertEqual(caught.exception.stage, 'permissions')
