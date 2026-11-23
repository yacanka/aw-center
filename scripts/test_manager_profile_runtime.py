"""Public desktop actions preserve selected inputs and existing SQLite data."""
from contextlib import closing, nullcontext
import importlib.util
import json
from pathlib import Path
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project
from scripts.manager import profile_runtime as runner


class ProfileRuntimeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.project = create_project(self.root)
        self.project.python.parent.mkdir(parents=True)
        self.project.python.touch()
        self.home = self.root / 'manager'
        self.enterContext(patch.object(runner.profiles, 'installation_home', return_value=self.home))
        self.enterContext(patch('scripts.manager.profile_resources.selected_project', return_value=self.project))
        self.values = dict(profile='dev', source_root=str(self.root), backend_port='8200', host='localhost')
        self.ask = Mock(return_value=('A12345', 'fixture-password'))
        self.notify = Mock()

    def test_env_wins_without_profile_or_source_location_requirement(self):
        path = self.project.backend / 'unrelated.local.env'
        content = ('AWCENTER_DEPLOYMENT_MODE=development\nPORT=8101\nDEV_BACKEND_PORT=8302\n'
                   'TLS_KEY_FILE=keys/elsewhere.key\nDEBUG=True\nSECRET_KEY=fixture\n')
        path.write_text(content)
        values = {**self.values, 'profile': 'prod', 'env_file': str(path)}
        self.assertEqual(runner.env_fields(values), {'backend_port': '8101', 'tls_key_file': 'keys/elsewhere.key'})
        connection = runner.effective_connection(values)
        self.assertEqual(connection['backend_port'], 8101)
        self.assertEqual(Path(connection['tls_key_file']), self.project.backend / 'keys/elsewhere.key')
        settings, *_ = runner._settings(self.project, values, connection, runner._selected(values))
        self.assertEqual(settings['AWCENTER_DEPLOYMENT_MODE'], 'development')
        self.assertEqual(settings['DEBUG'], 'True')
        self.assertEqual(path.read_text(), content)

    def test_existing_database_with_no_users_never_opens_admin_or_applies_migrations(self):
        database = self.project.backend / 'existing.sqlite3'
        database.write_bytes(b'preserved data')
        path = self.project.backend / 'selected.env'
        path.write_text('DATABASE_URL=sqlite:///existing.sqlite3\nSECRET_KEY=existing-db-key\n')
        with patch.object(runner.runtime, 'require_port'), patch.object(runner, '_django') as django, \
             patch.object(runner, '_serve') as serve:
            runner.execute('run', {**self.values, 'env_file': str(path)}, self.notify, self.ask)
        self.ask.assert_not_called()
        django.assert_not_called()
        self.assertEqual(serve.call_args.args[3]['SECRET_KEY'], 'existing-db-key')
        self.assertEqual(database.read_bytes(), b'preserved data')

    def test_empty_selected_value_remains_locked_and_control_keys_do_not_reach_children(self):
        path = self.project.backend / 'application.env'
        path.write_text('IPV4_ADDRESS=\nDEV_FRONTEND_PORT=unused\nAWCENTER_ENV_FILE=some-other-file\nPATH=untrusted\n')
        values = {**self.values, 'profile': 'prod', 'env_file': str(path)}
        self.assertEqual(runner.env_fields(values)['host'], '')
        self.assertNotIn('PATH', runner._selected(values))
        self.assertNotIn('AWCENTER_ENV_FILE', runner._selected(values))
        self.assertEqual(runner.effective_connection(values)['frontend_port'], 5173)
        with self.assertRaisesRegex(LauncherError, 'IPV4_ADDRESS'):
            runner.execute('run', values, self.notify, self.ask)

    def test_failed_first_admin_keeps_final_database_absent_and_retryable(self):
        database = self.project.backend / 'new.sqlite3'
        with patch.object(runner, '_django') as django, patch.object(runner, '_command', side_effect=LauncherError('admin')):
            with self.assertRaisesRegex(LauncherError, 'admin'):
                runner._first_database(self.project, database, {}, self.ask, self.notify)
        self.assertFalse(database.exists())
        self.assertNotEqual(django.call_args.args[1]['DATABASE_URL'], 'sqlite:///' + database.as_posix())
        with patch.object(runner, '_django'), patch.object(runner, '_command') as admin:
            runner._first_database(self.project, database, {}, self.ask, self.notify)
        self.assertTrue(database.is_file())
        self.assertEqual(json.loads(admin.call_args.kwargs['payload'])['username'], 'A12345')
        self.assertEqual(admin.call_args.args[0][-1], 'initial-admin-json')
        self.assertNotIn('fixture-password', str(admin.call_args.args))

    def test_missing_database_with_surviving_sqlite_journal_is_not_initialized(self):
        database = self.project.backend / 'existing.sqlite3'
        journal = database.with_name(database.name + '-wal')
        journal.write_bytes(b'existing-journal')
        with self.assertRaisesRegex(LauncherError, 'SQLite günlük'):
            runner._first_database(self.project, database, {}, self.ask, self.notify)
        self.ask.assert_not_called()
        self.assertFalse(database.exists())
        self.assertEqual(journal.read_bytes(), b'existing-journal')

    def test_each_gate_runs_only_its_selected_command(self):
        for field, args in [('deploy_check', ['check', '--deploy']), ('migration_check', ['migrate', '--check']),
                           ('collectstatic', ['collectstatic', '--noinput']), ('verify_frontend', ['verify_frontend_artifact'])]:
            with self.subTest(field=field), patch.object(runner, '_django') as django:
                runner._gates(self.project, {}, {}, self.notify)
                django.assert_not_called()
                runner._gates(self.project, {field: True}, {}, self.notify)
                django.assert_called_once_with(self.project, {}, args)

    def test_failed_gates_report_only_actionable_safe_fields(self):
        with patch.object(runner.process, 'controlled_run') as run:
            run.side_effect = [subprocess.CompletedProcess([], 1, '', ''),
                               subprocess.CompletedProcess([], 0, '[X] auth.0001_old\n[ ] users.0012_example\n', '')]
            with self.assertRaisesRegex(LauncherError, 'users.0012_example'):
                runner._django(self.project, {}, ['migrate', '--check'])
            run.side_effect = None
            run.return_value = subprocess.CompletedProcess([], 1, '', '(awcenter.E040) secret=raw-private-value\n')
            with self.assertRaisesRegex(LauncherError, 'awcenter.E040.*DEBUG=False') as failure:
                runner._django(self.project, {'EMAIL_HOST_PASSWORD': 'private'}, ['check', '--deploy'])
            self.assertNotIn('raw-private-value', str(failure.exception))
            self.assertEqual(run.call_args.kwargs['env']['EMAIL_HOST_PASSWORD'], '')
            run.return_value = subprocess.CompletedProcess([], 1, '', 'Collected frontend asset is missing or empty: assets/main.js\n')
            with self.assertRaisesRegex(LauncherError, 'assets/main.js'):
                runner._django(self.project, {}, ['verify_frontend_artifact'])

    def test_local_reload_controls_both_actual_start_commands(self):
        values = {**self.values, 'live_reload': False}
        vite_entry = self.project.frontend / 'node_modules/vite/bin/vite.js'
        vite_entry.parent.mkdir(parents=True)
        vite_entry.touch()
        with patch('scripts.manager.profile_resources.node_environment', return_value={'AWCENTER_MANAGED_NODE': 'node.exe'}), \
             patch.object(runner.process, 'server_console', return_value=nullcontext()), \
             patch.object(runner.process, 'start') as start, patch.object(runner, 'start_job_workers', return_value=[]), \
             patch.object(runner, '_ready'), patch.object(runner.process, 'supervise'):
            runner._serve(self.project, values, runner.effective_connection(values), {}, self.notify)
        web, vite = start.call_args_list
        self.assertIn('--noreload', web.args[0])
        self.assertEqual(vite.args[0][0], 'node.exe')
        self.assertEqual(vite.args[0][1].name, 'vite.js')
        self.assertEqual(vite.kwargs['extra_env']['AWCENTER_VITE_RELOAD'], '0')
        self.notify.assert_called_once_with('ready', 'http://localhost:5173/app/')

    def test_startup_diagnostic_returns_missing_module_and_withholds_other_output(self):
        failure = subprocess.CompletedProcess([], 1, '', "ModuleNotFoundError: No module named 'django'\npassword=private")
        with patch.object(runner.process, 'controlled_run', return_value=failure):
            message = runner._startup_diagnostic(self.project, {}, True)
        self.assertIn('Eksik Python modülü: django', message)
        self.assertNotIn('private', message)

    def test_relative_legacy_data_keys_and_new_database_defaults(self):
        home = runner.private_directory(self.home / 'config')
        legacy = {'DATABASE_URL': 'sqlite:///previous.sqlite3', 'SECRET_KEY': 'previous-db-key',
                  'JIRA_SESSION_ENCRYPTION_KEY': 'previous-jira-key'}
        runner.profiles._write_new(home / 'dev.env', runner.profiles._environment_content(legacy))
        path = self.project.backend / 'previous.sqlite3'
        path.touch()
        settings, database, stored = runner._settings(self.project, self.values, runner.effective_connection(self.values), {})
        runner._identity(self.project, self.home, database, settings, stored)
        self.assertEqual(path, database)
        self.assertEqual(settings['SECRET_KEY'], 'previous-db-key')
        prod = {**self.values, 'profile': 'prod'}
        _, prod_db, _ = runner._settings(self.project, prod, runner.effective_connection(prod), {})
        self.assertEqual(prod_db, self.home / 'state' / 'production' / 'db.sqlite3')

    def test_default_and_current_opposite_storage_are_reserved(self):
        custom_db = self.root / 'team+one.sqlite3'
        custom_media = self.root / 'documents'
        self.assertEqual(runner._sqlite_path(self.project.backend, runner._sqlite_url(custom_db)), custom_db)
        runner.claim_storage(self.project, 'prod', custom_db, custom_media)
        for db, media in [(custom_db, self.root / 'local-artifacts'), (self.root / 'local.sqlite3', custom_media / 'nested'),
                          (self.home / 'state/production/db.sqlite3', self.root / 'local-artifacts')]:
            with self.subTest(db=db, media=media), self.assertRaisesRegex(LauncherError, 'ayrı DATABASE_URL'):
                runner.claim_storage(self.project, 'dev', db, media)
        runner.claim_storage(self.project, 'prod', self.root / 'new.sqlite3', self.root / 'other-documents')
        runner.claim_storage(self.project, 'dev', custom_db, custom_media)

    def test_role_environments_preserve_notification_mail_without_vendor_credentials(self):
        from scripts.test_launcher_jobs import add_worker_command, add_auxiliary_worker_commands
        add_worker_command(self.project)
        add_auxiliary_worker_commands(self.project)
        config = {'AWCENTER_MAIL_TRANSPORT': 'django', 'AWCENTER_PASSWORD': 'shared-fixture',
                  'TEAMCENTER_PASSWORD': 'vendor-fixture', 'JIRA_SESSION_ENCRYPTION_KEY': 'jira-fixture'}
        with patch('scripts.launcher.job_worker.start') as start:
            runner.start_job_workers(self.project, config, protect_credentials=True, isolate_integrations=True)
        job, notification, cleanup = [call.kwargs['extra_env'] for call in start.call_args_list]
        self.assertEqual(job['EMAIL_HOST_PASSWORD'], '')
        self.assertEqual(notification['EMAIL_HOST_PASSWORD'], 'shared-fixture')
        self.assertEqual(cleanup['EMAIL_HOST_PASSWORD'], '')
        for env in (notification, cleanup):
            self.assertEqual(env['AWCENTER_PASSWORD'], '')
            self.assertEqual(env['TEAMCENTER_PASSWORD'], '')
            self.assertEqual(env['JIRA_ENABLED'], 'False')


@unittest.skipUnless(importlib.util.find_spec('django') and importlib.util.find_spec('cryptography'),
                     'requires the installed AW Center application dependencies')
class ProfileFirstStartIntegrationTests(unittest.TestCase):
    def test_actual_migrations_initial_admin_ipc_reopen_and_tls_pair(self):
        from scripts.manager.profile_resources import ProfileProject

        source = Path(__file__).resolve().parents[1]
        project = ProfileProject(source, source / 'backend/manage.py', source / 'frontend/package.json',
                                 source / 'requirements.txt', Path(sys.prefix))
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'private'
            db = Path(temp) / 'user data.sqlite3'
            with patch.object(runner.profiles, 'installation_home', return_value=home):
                values = {'profile': 'prod', 'host': '127.0.0.1', 'source_root': str(source)}
                connection = runner.effective_connection(values)
                settings, database, stored = runner._settings(project, values, connection,
                                               {'DATABASE_URL': 'sqlite:///' + db.as_posix()})
                runner._identity(project, home, database, settings, stored)
                admin = Mock(return_value=('A98765', 'Fixture-qG!13479'))
                runner._first_database(project, database, settings, admin, Mock())
                runner._first_database(project, database, settings, admin, Mock())
                admin.assert_called_once()
                with closing(sqlite3.connect(database)) as db_connection:
                    self.assertEqual(db_connection.execute('SELECT username FROM auth_user WHERE is_superuser=1').fetchall(),
                                     [('A98765',)])
                paths = runner._create_tls(project, connection)
                cert = paths['tls_cert_file']
                ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(cert, paths['tls_key_file'])
                self.assertIn(('IP Address', '127.0.0.1'), ssl._ssl._test_decode_cert(cert)['subjectAltName'])
                with self.assertRaises(LauncherError):
                    runner._create_tls(project, connection)
