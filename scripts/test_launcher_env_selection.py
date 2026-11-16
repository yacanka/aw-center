"""Explicit env selection imports configuration without rotating existing state."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher.installation_profiles import parse_environment, provision_profile, read_profile_environment
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project
from scripts.manager.operations import arguments
from scripts.manager.paths import normalize_task_paths
from scripts.manager.view_model import normalize_values


class EnvironmentSelectionTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
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
        with self.assertRaises(LauncherError) as caught:
            check_selected_environment(self.project, profile, self.selected)
        self.assertEqual(caught.exception.code, 'env_import_required')
        self.assertEqual(caught.exception.field, 'env_file')
        self.assertIn('AW Center’ı aç', caught.exception.remedy)
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

    def test_conventional_literal_syntax_imports_without_interpolation(self):
        content = (
            'export EMAIL_HOST = mail.example.invalid # mail server\n'
            "EMAIL_HOST_PASSWORD='literal # value ${UNCHANGED} $(literal)' # comment\n"
            'JIRA_URL=https://jira.example.invalid/#fragment\n'
        )
        self.selected.write_text(content, encoding='utf-8')
        with patch.dict(os.environ, {'UNCHANGED': 'must-not-expand'}):
            profile = provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        values = read_profile_environment(profile)
        self.assertEqual(values['EMAIL_HOST'], 'mail.example.invalid')
        self.assertEqual(values['EMAIL_HOST_PASSWORD'], 'literal # value ${UNCHANGED} $(literal)')
        self.assertEqual(values['JIRA_URL'], 'https://jira.example.invalid/#fragment')
        self.assertEqual(self.selected.read_text(), content)

    def test_inline_comment_can_follow_an_empty_value(self):
        self.assertEqual(parse_environment('JIRA_SESSION_ENCRYPTION_KEY= # generated when absent\n'),
                         {'JIRA_SESSION_ENCRYPTION_KEY': ''})

    def test_quoted_whitespace_and_comment_characters_remain_in_passwords(self):
        self.assertEqual(parse_environment('EMAIL_HOST_PASSWORD="  quoted # password  " # comment\n'),
                         {'EMAIL_HOST_PASSWORD': '  quoted # password  '})

    def test_single_and_double_quoted_windows_paths_remain_literal(self):
        for value in (r'"C:\Users\Example\DOORS\doors.exe"',
                      r'"C:\new\tools\doors.exe"',
                      r'"C:\u0041\tools\doors.exe"',
                      r'"C:\u0041"',
                      r"'C:\Users\Example\DOORS\doors.exe'",
                      r'"\\server\share\doors.exe"'):
            with self.subTest(value=value):
                parsed = parse_environment('DOORS_EXECUTABLE=' + value + ' # executable\n')
                self.assertEqual(parsed['DOORS_EXECUTABLE'], value[1:-1])

    def test_single_quoted_literal_can_end_with_a_backslash(self):
        for key, value in (('DOORS_DATABASE', 'C:\\data\\'),
                           ('EMAIL_HOST_PASSWORD', 'trailing\\')):
            with self.subTest(key=key):
                self.assertEqual(parse_environment(f"{key}='{value}' # literal value\n"), {key: value})

    def test_json_escaped_private_output_remains_readable(self):
        values = {'DOORS_EXECUTABLE': r'C:\new\tools\doors.exe',
                  'EMAIL_HOST_PASSWORD': 'quoted " value with \\ and Türkçe',
                  'DOORS_DATABASE': r'\\server\share\database'}
        content = ''.join(f'{key}={json.dumps(value, ensure_ascii=False)}\n' for key, value in values.items())
        self.assertEqual(parse_environment(content), values)

    def test_empty_optional_keys_preserve_generated_keys_on_fresh_profile(self):
        self.write(SECRET_KEY='', JIRA_SESSION_ENCRYPTION_KEY='   ', EMAIL_HOST='mail.example.invalid')
        profile = provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        values = read_profile_environment(profile)
        self.assertGreaterEqual(len(values['SECRET_KEY']), 80)
        self.assertEqual(len(base64.urlsafe_b64decode(values['JIRA_SESSION_ENCRYPTION_KEY'])), 32)
        self.assertEqual(values['EMAIL_HOST'], 'mail.example.invalid')

    def test_empty_optional_keys_preserve_existing_keys_and_database(self):
        profile = provision_profile(self.project, 'dev', self.home)
        before = read_profile_environment(profile)
        database = self.project.backend / 'db.sqlite3'
        database.write_bytes(b'existing-state')
        self.write(SECRET_KEY='', JIRA_SESSION_ENCRYPTION_KEY=' ', EMAIL_HOST='mail.example.invalid')
        updated = provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        values = read_profile_environment(updated)
        self.assertEqual(values['SECRET_KEY'], before['SECRET_KEY'])
        self.assertEqual(values['JIRA_SESSION_ENCRYPTION_KEY'], before['JIRA_SESSION_ENCRYPTION_KEY'])
        self.assertEqual(database.read_bytes(), b'existing-state')

    def test_duplicate_keys_report_only_key_and_line_before_any_write(self):
        self.selected.write_text('EMAIL_HOST=private-first\nexport EMAIL_HOST=private-second\n', encoding='utf-8')
        with self.assertRaises(LauncherError) as caught:
            provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        self.assertEqual(getattr(caught.exception, 'code', None), 'env_file_invalid')
        self.assertEqual(getattr(caught.exception, 'field', None), 'env_file')
        self.assertEqual(getattr(caught.exception, 'line', None), 2)
        self.assertIn('EMAIL_HOST', str(caught.exception))
        self.assertNotIn('private-first', str(caught.exception))
        self.assertNotIn('private-second', str(caught.exception))
        self.assertFalse(self.home.exists())

    def test_invalid_syntax_and_control_values_report_safe_line_numbers(self):
        for content, line in (('EMAIL_HOST=valid\nexport lower_key=private-value\n', 2),
                              ('EMAIL_HOST="unterminated-private-value\n', 1),
                              ('EMAIL_HOST="bad\\tprivate-value"\n', 1)):
            with self.subTest(content=content), self.assertRaises(LauncherError) as caught:
                parse_environment(content)
            self.assertEqual(getattr(caught.exception, 'code', None), 'env_file_invalid')
            self.assertEqual(getattr(caught.exception, 'line', None), line)
            self.assertNotIn('private-value', str(caught.exception))

    def test_different_managed_state_reports_keys_and_preserves_profile(self):
        profile = provision_profile(self.project, 'dev', self.home)
        before = Path(profile['env_file']).read_bytes()
        self.write(DATABASE_URL='sqlite:///private-foreign.sqlite3', PRIVATE_MEDIA_ROOT='/private-foreign-media', PORT='9000')
        with self.assertRaises(LauncherError) as caught:
            provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        self.assertEqual(getattr(caught.exception, 'code', None), 'env_managed_setting_conflict')
        self.assertEqual(getattr(caught.exception, 'keys', None), ('DATABASE_URL', 'PORT', 'PRIVATE_MEDIA_ROOT'))
        self.assertEqual(getattr(caught.exception, 'field', None), 'env_file')
        self.assertTrue(getattr(caught.exception, 'remedy', None))
        for key in ('DATABASE_URL', 'PRIVATE_MEDIA_ROOT', 'PORT'):
            self.assertIn(key, str(caught.exception))
        self.assertNotIn('private-foreign', str(caught.exception))
        self.assertEqual(Path(profile['env_file']).read_bytes(), before)

    def test_startup_control_keys_report_names_without_values(self):
        self.write(PYTHONPATH='/private-startup-code', NODE_OPTIONS='--require=private-code')
        with self.assertRaises(LauncherError) as caught:
            provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        self.assertEqual(getattr(caught.exception, 'code', None), 'env_process_setting_forbidden')
        self.assertEqual(getattr(caught.exception, 'keys', None), ('NODE_OPTIONS', 'PYTHONPATH'))
        self.assertNotIn('private-startup-code', str(caught.exception))
        self.assertNotIn('private-code', str(caught.exception))
        self.assertFalse(self.home.exists())

    def test_nonempty_existing_key_conflict_reports_names_without_rotation(self):
        profile = provision_profile(self.project, 'dev', self.home)
        before = Path(profile['env_file']).read_bytes()
        self.write(SECRET_KEY='private-replacement-key')
        with self.assertRaises(LauncherError) as caught:
            provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        self.assertEqual(getattr(caught.exception, 'code', None), 'env_identity_conflict')
        self.assertEqual(getattr(caught.exception, 'keys', None), ('SECRET_KEY',))
        self.assertNotIn('private-replacement-key', str(caught.exception))
        self.assertEqual(Path(profile['env_file']).read_bytes(), before)

    def test_blank_keys_cannot_adopt_an_existing_manual_database(self):
        database = self.project.backend / 'db.sqlite3'
        database.write_bytes(b'existing-state')
        self.write(SECRET_KEY='', JIRA_SESSION_ENCRYPTION_KEY=' ')
        with self.assertRaises(LauncherError):
            provision_profile(self.project, 'dev', self.home, env_file=self.selected)
        self.assertEqual(database.read_bytes(), b'existing-state')
        self.assertFalse(self.home.exists())


if __name__ == '__main__':
    unittest.main()
