"""Only non-secret desktop inputs survive a Manager restart."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.launcher.installation_permissions import secure_path
from scripts.launcher.model import LauncherError


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.preferences = importlib.import_module('scripts.manager.preferences')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve() / 'AWCenter'

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
        raw = (self.home / 'config/manager.json').read_text(encoding='utf-8')
        self.assertNotIn('must-not-persist', raw)

    def test_credential_urls_are_not_persisted_even_in_disabled_fields(self):
        self.preferences.save_preferences(self.home, {'source_mode': 'offline',
            'python_index_url': 'https://user:private@packages.example/simple',
            'npm_registry_url': 'https://npm.example?token=private',
            'repository': 'https://packages.example/#private'})
        raw = (self.home / 'config/manager.json').read_text(encoding='utf-8')
        self.assertNotIn('private', raw)
        self.assertEqual(self.preferences.load_preferences(self.home)['source_mode'], 'offline')

    def test_empty_and_corrupted_preferences_do_not_provision_application_state(self):
        self.assertEqual(self.preferences.load_preferences(self.home), {})
        self.assertFalse(self.home.exists())
        self.preferences.save_preferences(self.home, {'profile': 'dev'})
        path = self.home / 'config/manager.json'
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
        path = self.home / 'config/manager.json'
        path.unlink()
        try:
            path.symlink_to(target)
        except OSError:
            self.skipTest('Symlinks are unavailable to the current Windows user')
        with self.assertRaises(LauncherError):
            self.preferences.save_preferences(self.home, {'profile': 'prod'})
        self.assertEqual(target.read_text(encoding='utf-8'), 'original')
