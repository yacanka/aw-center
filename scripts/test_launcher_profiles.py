"""Private installation profiles must preserve keys, state and OS boundaries."""

import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.launcher.model import LauncherError, Project
from scripts.launcher import installation_profiles as profiles
from scripts.launcher.installation_permissions import require_private, secure_path


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        source = self.root / 'source'
        (source / 'backend').mkdir(parents=True)
        (source / 'frontend').mkdir()
        self.project = Project(source, source / 'backend/manage.py', source / 'frontend/package.json', None)
        self.home = self.root / 'AWCenter'
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def provision(self, name='dev', **options):
        return profiles.provision_profile(self.project, name, self.home, **options)

    def test_dev_is_explicit_loopback_and_keys_never_enter_json(self):
        profile = self.provision()
        values = profiles.read_environment(Path(profile['env_file']))
        self.assertEqual(profile['host'], '127.0.0.1')
        self.assertEqual(profile['backend_port'], 8000)
        self.assertEqual(values['DEBUG'], 'True')
        self.assertEqual(values['ALLOW_ALL_DEBUG_HOSTS'], 'False')
        self.assertEqual(values['DATABASE_URL'], 'sqlite:///' + (self.project.backend / 'db.sqlite3').as_posix())
        self.assertGreaterEqual(len(values['SECRET_KEY']), 80)
        self.assertEqual(len(base64.urlsafe_b64decode(values['JIRA_SESSION_ENCRYPTION_KEY'])), 32)
        self.assertNotEqual(values['SECRET_KEY'], values['JIRA_SESSION_ENCRYPTION_KEY'])
        document = (self.home / 'config/dev.profile.json').read_text()
        self.assertNotIn(values['SECRET_KEY'], document)
        self.assertFalse(any(key.startswith('AI_API_') for key in values))
        self.assertFalse((self.project.backend / 'db.sqlite3').exists())
        require_private(Path(profile['env_file']))
        require_private(self.home / 'config')

    def test_existing_profile_is_byte_identical_and_wrong_source_rejected(self):
        profile = self.provision()
        before = {path: path.read_bytes() for path in (self.home / 'config').iterdir()}
        self.assertEqual(profile, self.provision())
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        other = Project(self.root / 'other', self.root / 'other/backend/manage.py', self.root / 'other/frontend/package.json', None)
        with self.assertRaises(LauncherError):
            profiles.load_profile(other, 'dev', self.home)

    def test_process_conflicts_block_without_values_in_error(self):
        profile = self.provision()
        for key, value in [('SECRET_KEY', 'never-print-this'), ('DATABASE_URL', 'sqlite:///another.sqlite3'), ('AI_API_URL', 'https://private.example')]:
            with self.subTest(key=key), mock.patch.dict(os.environ, {key: value}):
                with self.assertRaises(LauncherError) as caught:
                    profiles.profile_environment(profile)
                self.assertNotIn(value, str(caught.exception))
        environment = profiles.profile_environment(profile)
        self.assertEqual(environment['AWCENTER_ENV_FILE'], profile['env_file'])
        self.assertEqual(environment['IPV4_ADDRESS'], '127.0.0.1')

    def test_installer_owned_process_variables_are_not_application_overrides(self):
        profile = self.provision()
        with mock.patch.dict(os.environ, {'AWCENTER_MANAGED_PYTHON': 'managed-python', 'AWCENTER_MANAGED_NODE': 'managed-node', 'AWCENTER_PACKAGE_REPOSITORY': 'https://packages.example', 'AWCENTER_OFFLINE_DIR': 'offline'}):
            self.assertEqual(profiles.profile_environment(profile)['AWCENTER_ENV_FILE'], profile['env_file'])

    def test_doctor_missing_profile_is_read_only(self):
        result = profiles.inspect_profile(self.project, {'name': 'dev', 'env_file': str(self.home / 'config/dev.env')})
        self.assertTrue(any(item['status'] == 'missing' for item in result))
        self.assertFalse(self.home.exists())

    def test_rejects_symlink_ancestor_and_does_not_follow_it(self):
        real = self.root / 'real'
        real.mkdir()
        link = self.root / 'link'
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(LauncherError):
            profiles.provision_profile(self.project, 'dev', link / 'AWCenter')
        self.assertEqual(list(real.iterdir()), [])

    def test_rejects_unsafe_existing_permissions_without_repair(self):
        if os.name == 'nt':
            self.skipTest('POSIX mode test; Win32 ACL is checked by native smoke')
        profile = self.provision()
        env = Path(profile['env_file'])
        env.chmod(0o644)
        with self.assertRaises(LauncherError):
            profiles.load_profile(self.project, 'dev', self.home)
        self.assertEqual(env.stat().st_mode & 0o777, 0o644)

    def test_orphan_environment_is_not_overwritten(self):
        config = self.home / 'config'
        config.mkdir(parents=True)
        secure_path(self.home)
        secure_path(config)
        path = config / 'dev.env'
        path.write_text('SECRET_KEY=existing\n')
        secure_path(path)
        with self.assertRaises(LauncherError):
            self.provision()
        self.assertEqual(path.read_text(), 'SECRET_KEY=existing\n')

    def test_interrupted_provision_recovers_existing_keys_from_owned_pending_metadata(self):
        write = profiles._write_new
        def interrupted(path, content):
            if path.name == 'dev.profile.json':
                raise OSError('synthetic interruption after environment publication')
            return write(path, content)
        with mock.patch.object(profiles, '_write_new', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.provision()
        environment = self.home / 'config/dev.env'
        before = environment.read_bytes()
        pending = self.home / 'config/dev.pending.json'
        self.assertTrue(pending.exists())
        require_private(pending)
        self.assertNotIn(profiles.read_environment(environment)['SECRET_KEY'], pending.read_text())
        recovered = self.provision()
        self.assertEqual(environment.read_bytes(), before)
        self.assertFalse(pending.exists())
        self.assertEqual(recovered['env_file'], str(environment))

    def test_pending_provision_before_environment_publication_can_retry(self):
        write = profiles._write_new
        def interrupted(path, content):
            if path.name == 'dev.env':
                raise OSError('synthetic interruption before environment publication')
            return write(path, content)
        with mock.patch.object(profiles, '_write_new', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.provision()
        self.assertFalse((self.home / 'config/dev.env').exists())
        self.assertTrue((self.home / 'config/dev.pending.json').exists())
        recovered = self.provision()
        self.assertTrue(Path(recovered['env_file']).exists())
        self.assertFalse((self.home / 'config/dev.pending.json').exists())

    def test_pending_recovery_refuses_changed_environment_without_replacing_keys(self):
        write = profiles._write_new
        def interrupted(path, content):
            if path.name == 'dev.profile.json':
                raise OSError('synthetic interrupted finalization')
            return write(path, content)
        with mock.patch.object(profiles, '_write_new', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.provision()
        environment = self.home / 'config/dev.env'
        environment.write_text(environment.read_text() + '# operator edit\n')
        before = environment.read_bytes()
        with self.assertRaises(LauncherError):
            self.provision()
        self.assertEqual(environment.read_bytes(), before)
        self.assertFalse((self.home / 'config/dev.profile.json').exists())

    def test_existing_manual_environment_and_database_require_explicit_adoption(self):
        database = self.project.backend / 'db.sqlite3'
        environment = self.project.backend / '.env'
        database.write_bytes(b'existing database state')
        environment.write_text('SECRET_KEY=existing-private-value\n')
        with self.assertRaises(LauncherError) as caught:
            self.provision()
        self.assertIn('adoption', str(caught.exception))
        self.assertNotIn('existing-private-value', str(caught.exception))
        self.assertFalse(self.home.exists())
        self.assertEqual(database.read_bytes(), b'existing database state')

    def test_environment_write_failure_never_publishes_a_partial_file(self):
        directory = self.root / 'private'
        directory.mkdir()
        secure_path(directory)
        destination = directory / 'new.env'
        with mock.patch.object(profiles.os, 'fsync', side_effect=OSError('synthetic interrupted write')):
            with self.assertRaises(OSError):
                profiles._write_new(destination, 'SECRET_KEY=synthetic-value\n')
        self.assertFalse(destination.exists())

    def test_explicit_asset_rebind_preserves_keys_database_and_private_configuration(self):
        profile = self.provision()
        path = Path(profile['env_file'])
        with path.open('a') as stream:
            stream.write('TEAMCENTER_BASE_URL="https://private.example"\n')
        before = profiles.read_environment(path)
        updated = profiles.update_asset_set(self.project, profile, 'approved-v2')
        after = profiles.read_environment(path)
        self.assertEqual(updated['asset_set'], 'approved-v2')
        changed = {'MODEL_RUNTIME_DIR', 'CUSTOM_TEMPLATE_DIR',
                   'WORD_TRANSLATION_TR_EN_MODEL', 'WORD_TRANSLATION_EN_TR_MODEL',
                   'WORD_ANALYZER_BI_MODEL', 'WORD_ANALYZER_CROSS_MODEL', 'COVER_PAGE_TEMPLATE_PATH'}
        self.assertEqual({key:value for key,value in before.items() if key not in changed},
                         {key:value for key,value in after.items() if key not in changed})
        for key in changed:
            self.assertIn('/assets/sets/approved-v2/', after[key])
        self.assertEqual(profiles.load_profile(self.project, 'dev', self.home), updated)
        self.assertEqual(self.provision(asset_set='silently-ignored')['asset_set'], 'approved-v2')
        self.assertFalse((self.project.backend / 'db.sqlite3').exists())

    def test_invalid_asset_rebind_is_read_only(self):
        profile = self.provision()
        before = {path:path.read_bytes() for path in (self.home / 'config').iterdir()}
        with self.assertRaises(LauncherError):
            profiles.update_asset_set(self.project, profile, '../escape')
        self.assertEqual(before, {path:path.read_bytes() for path in (self.home / 'config').iterdir()})

    def test_interrupted_asset_rebind_recovers_without_rotating_keys(self):
        profile = self.provision()
        before = profiles.read_environment(Path(profile['env_file']))
        replace = profiles._write_replace
        def interrupted(path, content):
            if path.name == 'dev.profile.json':
                raise OSError('synthetic interruption after environment replacement')
            return replace(path, content)
        with mock.patch.object(profiles, '_write_replace', side_effect=interrupted):
            with self.assertRaises(OSError):
                profiles.update_asset_set(self.project, profile, 'approved-v2')
        recovered = self.provision()
        after = profiles.read_environment(Path(profile['env_file']))
        self.assertEqual(recovered['asset_set'], 'approved-v2')
        self.assertEqual(before['SECRET_KEY'], after['SECRET_KEY'])
        self.assertEqual(before['JIRA_SESSION_ENCRYPTION_KEY'], after['JIRA_SESSION_ENCRYPTION_KEY'])
        self.assertEqual(before['DATABASE_URL'], after['DATABASE_URL'])
        self.assertFalse((self.home / 'config/dev.pending.json').exists())

    def test_prod_requires_explicit_host_and_tls(self):
        with self.assertRaises(LauncherError):
            self.provision('prod')
        with self.assertRaises(LauncherError):
            self.provision(host='0.0.0.0')
        self.assertFalse(self.home.exists())

    def test_prod_state_and_secrets_are_separate_and_assets_canonical(self):
        dev = self.provision()
        certificate = self.root / 'certificate.pem'
        key = self.root / 'key.pem'
        certificate.write_text('operator supplied')
        key.write_text('operator supplied')
        release = self.home / 'releases/approved-1/source'
        (release / 'backend').mkdir(parents=True)
        (release / 'frontend').mkdir()
        prod_project = Project(release, release / 'backend/manage.py', release / 'frontend/package.json', None)
        secure_path(self.home)
        prod = profiles.provision_profile(prod_project, 'prod', self.home, host='192.0.2.10', tls_cert_file=certificate, tls_key_file=key, asset_set='approved-1')
        dev_values = profiles.read_environment(Path(dev['env_file']))
        values = profiles.read_environment(Path(prod['env_file']))
        self.assertNotEqual(values['SECRET_KEY'], dev_values['SECRET_KEY'])
        self.assertNotEqual(values['JIRA_SESSION_ENCRYPTION_KEY'], dev_values['JIRA_SESSION_ENCRYPTION_KEY'])
        self.assertIn('/state/production/', values['DATABASE_URL'])
        for name in ('private_media', 'cache', 'staticfiles', 'media'):
            require_private(self.home / 'state/production' / name)
        self.assertFalse((self.home / 'assets').exists())
        self.assertIn('/assets/sets/approved-1/', values['MODEL_RUNTIME_DIR'])
        self.assertEqual(values['AWCENTER_DEPLOYMENT_MODE'], 'windows-native')
        env_path = Path(prod['env_file'])
        env_path.write_text(env_path.read_text().replace(values['SECRET_KEY'], dev_values['SECRET_KEY']))
        with self.assertRaises(LauncherError):
            profiles.load_profile(prod_project, 'prod', self.home)

    def test_prod_refuses_the_development_source_and_virtual_environment(self):
        self.provision()
        certificate = self.root / 'certificate.pem'
        key = self.root / 'key.pem'
        certificate.write_text('operator supplied')
        key.write_text('operator supplied')
        with self.assertRaises(LauncherError):
            self.provision('prod', host='192.0.2.10', tls_cert_file=certificate, tls_key_file=key)
        self.assertFalse((self.home / 'config/prod.env').exists())

    def test_invalid_zero_port_and_asset_traversal_are_refused(self):
        for options in ({'backend_port': 0}, {'asset_set': '../other'}):
            with self.subTest(options=options), self.assertRaises(LauncherError):
                self.provision(**options)
        self.assertFalse(self.home.exists())

    def test_per_model_paths_cannot_escape_the_selected_asset_set(self):
        profile = self.provision()
        env = Path(profile['env_file'])
        with env.open('a') as stream:
            stream.write('WORD_ANALYZER_BI_MODEL=/outside/selected/assets\n')
        with self.assertRaises(LauncherError):
            profiles.load_profile(self.project, 'dev', self.home)

    def test_modified_wildcard_development_hosts_are_refused(self):
        profile = self.provision()
        env = Path(profile['env_file'])
        env.write_text(env.read_text().replace('ALLOWED_HOSTS="127.0.0.1,localhost"', 'ALLOWED_HOSTS="*"'))
        with self.assertRaises(LauncherError):
            profiles.load_profile(self.project, 'dev', self.home)

    def test_rejects_profile_json_env_redirection(self):
        profile = self.provision()
        path = self.home / 'config/dev.profile.json'
        data = json.loads(path.read_text())
        data['env_file'] = str(self.root / 'elsewhere.env')
        path.write_text(json.dumps(data))
        with self.assertRaises(LauncherError):
            profiles.load_profile(self.project, 'dev', self.home)


if __name__ == '__main__':
    unittest.main()


class ReadOnlyProbeTests(unittest.TestCase):
    def test_missing_sqlite_inspection_does_not_create_file_or_directory(self):
        from scripts.launcher.installation_probe import inspect_sqlite
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary).resolve() / 'missing' / 'db.sqlite3'
            result = inspect_sqlite(database, {('auth', '0001_initial')})
            self.assertEqual(result['schema'], 'missing')
            self.assertIsNone(result['admin_exists'])
            self.assertFalse(database.parent.exists())

    def test_inspection_reports_pending_and_active_admin_without_writes(self):
        import sqlite3
        from scripts.launcher.installation_probe import inspect_sqlite
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / 'db.sqlite3'
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE django_migrations (app text, name text)')
                connection.execute("INSERT INTO django_migrations VALUES ('auth','0001_initial')")
                connection.execute('CREATE TABLE auth_user (is_superuser bool, is_active bool)')
                connection.execute('INSERT INTO auth_user VALUES (1,1)')
            before = path.read_bytes()
            result = inspect_sqlite(path, {('auth','0001_initial'), ('users','0001_initial')})
            self.assertEqual(result['schema'], 'pending')
            self.assertTrue(result['admin_exists'])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([item.name for item in path.parent.iterdir()], ['db.sqlite3'])

    def test_wal_database_is_not_inspected_with_stale_snapshot(self):
        from scripts.launcher.installation_probe import inspect_sqlite
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / 'db.sqlite3'
            path.write_bytes(b'not a database')
            Path(str(path) + '-wal').write_bytes(b'busy')
            result = inspect_sqlite(path, set())
            self.assertEqual(result['schema'], 'error')

    def test_real_probe_missing_db_does_not_create_storage(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            environment = os.environ.copy()
            environment.update(AWCENTER_ENV_FILE=os.devnull, SECRET_KEY='isolated-probe-fixture', DEBUG='True', DATABASE_URL='sqlite:///' + (root / 'absent/db.sqlite3').as_posix(), PRIVATE_MEDIA_ROOT=str(root / 'absent/private_media'), CACHE_DIRECTORY=str(root / 'absent/cache'), PYTHONDONTWRITEBYTECODE='1')
            completed = subprocess.run([sys.executable, '-m', 'scripts.launcher.installation_probe', 'inspect'], cwd=Path(__file__).resolve().parents[1], env=environment, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)['schema'], 'missing')
            self.assertEqual(list(root.iterdir()), [])
