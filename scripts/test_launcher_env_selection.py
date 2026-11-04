"""Explicit env selection imports configuration without rotating existing state."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from scripts.launcher.installation_profiles import provision_profile, read_profile_environment
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project
from scripts.manager.operations import arguments
from scripts.manager.paths import normalize_task_paths
from scripts.manager.view_model import normalize_values


class EnvironmentSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        self.project = create_project(self.source)
        self.home = self.root / 'private'
        self.selected = self.root / 'chosen.env'

    def write(self, **values):
        self.selected.write_text(''.join(f'{key}={json.dumps(value)}\n' for key, value in values.items()), encoding='utf-8')
        return self.selected.read_bytes()

    def test_form_and_worker_preserve_selected_path_only_for_relevant_actions(self):
        values = normalize_values('provision', {'env_file': 'chosen.env'})
        self.assertEqual(values.get('env_file'), 'chosen.env')
        self.assertTrue(Path(normalize_task_paths(values)['env_file']).is_absolute())
        for action in ('provision', 'start', 'doctor'):
            self.assertEqual(arguments({'action': action, 'env_file': str(self.selected)}).env_file, self.selected)
        self.assertIsNone(arguments({'action': 'test-sources', 'env_file': ['irrelevant']}).env_file)

    def test_fresh_profile_imports_values_keeps_source_and_secures_runtime_copy(self):
        content = self.write(SECRET_KEY='fixture-application-secret',
                             JIRA_SESSION_ENCRYPTION_KEY=base64.urlsafe_b64encode(b'k' * 32).decode(),
                             EMAIL_HOST='mail.example.invalid')
        profile = provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        values = read_profile_environment(profile)
        self.assertEqual(values['SECRET_KEY'], 'fixture-application-secret')
        self.assertEqual(values['EMAIL_HOST'], 'mail.example.invalid')
        self.assertEqual(self.selected.read_bytes(), content)
        self.assertNotEqual(Path(profile['env_file']), self.selected)

    def test_reimport_preserves_keys_and_database(self):
        profile = provision_profile(self.project, 'dev', self.home)
        initial = read_profile_environment(profile)
        database = self.project.backend / 'db.sqlite3'
        database.write_bytes(b'unchanged-database-fixture')
        content = self.write(EMAIL_HOST='mail.example.invalid')
        updated = provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        values = read_profile_environment(updated)
        for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY', 'DATABASE_URL'):
            self.assertEqual(values[key], initial[key])
        self.assertEqual(database.read_bytes(), b'unchanged-database-fixture')
        self.assertEqual(self.selected.read_bytes(), content)
        self.assertEqual(values.get('EMAIL_HOST'), 'mail.example.invalid')

    def test_different_existing_secret_is_rejected_without_any_write(self):
        profile = provision_profile(self.project, 'dev', self.home)
        before = Path(profile['env_file']).read_bytes()
        self.write(SECRET_KEY='never-echo-or-apply-this')
        with self.assertRaises(LauncherError) as caught:
            provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        self.assertNotIn('never-echo-or-apply-this', str(caught.exception))
        self.assertEqual(Path(profile['env_file']).read_bytes(), before)

    def test_incompatible_state_or_startup_injection_is_rejected_before_creation(self):
        for key, value in (('DATABASE_URL', 'sqlite:///foreign.sqlite3'), ('PYTHONPATH', '/foreign-code'),
                           ('AWCENTER_ENV_FILE', '/foreign.env'), ('NODE_OPTIONS', '--require=foreign'),
                           ('SYSTEMROOT', '/foreign-system'), ('AWCENTER_MANAGED_PYTHON', '/foreign/python')):
            self.write(**{key: value})
            with self.subTest(key=key), self.assertRaises(LauncherError):
                provision_profile(self.project, 'dev', self.home, env_file=self.selected)
            self.assertFalse(self.home.exists())

    def test_selected_file_parse_errors_are_not_echoed(self):
        self.selected.write_text('SECRET_KEY="secret-value\n', encoding='utf-8')
        with self.assertRaises(LauncherError) as caught:
            provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        self.assertNotIn('secret-value', str(caught.exception))
        self.assertFalse(self.home.exists())

    def test_readonly_start_requires_reimport_when_source_settings_changed(self):
        from scripts.launcher.installation_env import check_selected_environment
        self.write(EMAIL_HOST='mail.example.invalid')
        profile = provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        before = Path(profile['env_file']).read_bytes()
        check_selected_environment(self.project, profile, self.selected)
        self.write(EMAIL_HOST='changed.example.invalid')
        with self.assertRaisesRegex(LauncherError, 'Kur ve başlat'):
            check_selected_environment(self.project, profile, self.selected)
        self.assertEqual(Path(profile['env_file']).read_bytes(), before)

    def test_existing_manual_database_requires_both_original_keys(self):
        database = self.project.backend / 'db.sqlite3'
        database.write_bytes(b'existing-state')
        (self.project.backend / '.env').write_text('# existing manual configuration')
        self.write(EMAIL_HOST='mail.example.invalid')
        with self.assertRaises(LauncherError):
            provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        self.assertFalse(self.home.exists())
        self.assertEqual(database.read_bytes(), b'existing-state')

    def test_explicit_manual_adoption_keeps_supplied_keys_and_existing_database(self):
        database = self.project.backend / 'db.sqlite3'
        database.write_bytes(b'existing-state')
        old_env = self.project.backend / '.env'
        old_env.write_text('# original file remains unchanged')
        self.write(SECRET_KEY='fixture-existing-key',
                   JIRA_SESSION_ENCRYPTION_KEY=base64.urlsafe_b64encode(b'k' * 32).decode())
        profile = provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        self.assertEqual(read_profile_environment(profile)['SECRET_KEY'], 'fixture-existing-key')
        self.assertEqual(read_profile_environment(profile)['JIRA_SESSION_ENCRYPTION_KEY'], base64.urlsafe_b64encode(b'k' * 32).decode())
        self.assertEqual(database.read_bytes(), b'existing-state')
        self.assertEqual(old_env.read_text(), '# original file remains unchanged')

    def test_utf8_bom_is_supported_and_duplicate_or_oversized_files_are_rejected(self):
        self.selected.write_text('EMAIL_HOST=mail.example.invalid\n', encoding='utf-8-sig')
        profile = provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        before = Path(profile['env_file']).read_bytes()
        for invalid in ('EMAIL_HOST=one\nEMAIL_HOST=two\n', 'EMAIL_HOST="bad\\tvalue"\n',
                        '# ' + 'x' * (128 * 1024)):
            self.selected.write_text(invalid, encoding='utf-8')
            with self.assertRaises(LauncherError):
                provision_profile(self.project, 'dev', self.home, env_file=self.selected)
            self.assertEqual(Path(profile['env_file']).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
