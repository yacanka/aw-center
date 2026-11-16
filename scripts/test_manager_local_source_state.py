"""Packaged local state must not become unexpected source on the next open."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import test_manager_payload as fixtures
from scripts.launcher import installation_profiles as profiles
from scripts.launcher.model import LauncherError
from scripts.manager import operations


class LocalSourceStateTests(unittest.TestCase):
    setUp = fixtures.PayloadTests.setUp
    prepare = fixtures.PayloadTests.prepare

    def make_local(self):
        self.project.package_json.write_text('{"dependencies":{"vue":"3"}}')
        source = self.prepare()
        self.home = self.root / 'private'
        location = patch.object(profiles, 'installation_home', return_value=self.home)
        location.start()
        self.addCleanup(location.stop)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        return source

    def args(self, source, env_file):
        args = operations.arguments({'action': 'ensure', 'source_root': str(source),
                                     'env_file': str(env_file)})
        args.source_root = str(source)
        args.progress = lambda _message: None
        return args

    def select_source(self, source, args):
        with patch.object(operations.sys, 'frozen', True, create=True), \
             patch('scripts.launcher.installation.require_windows'):
            return operations._project_for('doctor', args)

    def test_existing_local_state_is_accepted_without_weakening_source_checks(self):
        from scripts.launcher.installation_local_config import apply_local_configuration
        from scripts.launcher.discovery import discover_project
        source = self.make_local()
        env_file = self.root / 'local.env'
        env_file.write_text('PORT=18401\nDEV_FRONTEND_PORT=15401\n'
                            'DATABASE_URL=sqlite:///custom.sqlite3\n'
                            'PRIVATE_MEDIA_ROOT=custom-private\nCACHE_DIRECTORY=custom-cache\n')
        args = self.args(source, env_file)
        profile = apply_local_configuration(discover_project(source), args)
        (source / 'backend/custom.sqlite3').write_bytes(b'local database fixture')
        for name in ('custom-private', 'custom-cache'):
            directory = source / 'backend' / name
            directory.mkdir()
            (directory / 'artifact.bin').write_bytes(b'local artifact fixture')

        self.assertEqual(self.select_source(source, args).root, source)

        (source / 'backend/manage.py').write_text('# changed source\n')
        with self.assertRaises(LauncherError):
            self.select_source(source, args)
        self.assertEqual(profiles.read_profile_environment(profile)['DATABASE_URL'],
                         'sqlite:///' + (source / 'backend/custom.sqlite3').as_posix())

    def test_switching_database_keeps_old_generated_state_valid(self):
        from scripts.launcher.installation_local_config import apply_local_configuration
        from scripts.launcher.discovery import discover_project
        source = self.make_local()
        project = discover_project(source)
        env_file = self.root / 'switch.env'
        args = self.args(source, env_file)
        for database, media in (('first.sqlite3', 'first-media'), ('second.sqlite3', 'second-media')):
            env_file.write_text(f'PORT=18402\nDEV_FRONTEND_PORT=15402\nDATABASE_URL=sqlite:///{database}\n'
                                f'PRIVATE_MEDIA_ROOT={media}\n')
            apply_local_configuration(project, args)
            (source / 'backend' / database).write_bytes(b'existing local database fixture')
            directory = source / 'backend' / media
            directory.mkdir()
            (directory / 'output.bin').write_bytes(b'previous user output')

        self.assertEqual(self.select_source(source, args).root, source)
        self.assertEqual((source / 'backend/first-media/output.bin').read_bytes(), b'previous user output')

    def test_first_source_env_inside_package_is_not_treated_as_source_code(self):
        source = self.make_local()
        env_file = source / 'backend' / '.env.local'
        content = 'PORT=18403\nDEV_FRONTEND_PORT=15403\n'
        env_file.write_text(content)

        self.assertEqual(self.select_source(source, self.args(source, env_file)).root, source)

        self.assertEqual(env_file.read_text(), content)
        self.assertFalse(self.home.exists())

    def test_local_exemptions_cannot_hide_manifest_owned_source(self):
        source = self.make_local()
        for state in ({'files': ['backend/manage.py'], 'directories': []},
                      {'files': [], 'directories': ['backend']}):
            with self.subTest(state=state), self.assertRaises(LauncherError):
                self.payload.verify_source_payload(source, local_state=state)

    def test_interrupted_published_env_can_reach_managed_recovery(self):
        from scripts.launcher.installation_local_config import apply_local_configuration
        from scripts.launcher.discovery import discover_project
        from scripts.manager import ensure
        source = self.make_local()
        project = discover_project(source)
        env_file = self.root / 'recover.env'
        env_file.write_text('PORT=18404\nDEV_FRONTEND_PORT=15404\nDATABASE_URL=sqlite:///first.sqlite3\n')
        args = self.args(source, env_file)
        apply_local_configuration(project, args)
        (source / 'backend/first.sqlite3').write_bytes(b'previous database')
        env_file.write_text('PORT=18404\nDEV_FRONTEND_PORT=15404\nDATABASE_URL=sqlite:///second.sqlite3\n')
        replace = profiles._write_replace
        def interrupt(path, content):
            if path.name == 'dev.profile.json':
                raise OSError('synthetic metadata interruption')
            return replace(path, content)
        with patch.object(profiles, '_write_replace', side_effect=interrupt), self.assertRaises(OSError):
            apply_local_configuration(project, args)
        pending = self.home / 'config/dev.pending.json'
        before = pending.read_bytes()

        with patch.object(operations.sys, 'frozen', True, create=True), \
             patch('scripts.launcher.installation.require_windows'):
            self.assertEqual(ensure._initial_action(args), 'provision')

        self.assertEqual(pending.read_bytes(), before)
        recovered = profiles.provision_profile(project, 'dev', self.home)
        self.assertTrue(profiles.read_profile_environment(recovered)['DATABASE_URL'].endswith('/second.sqlite3'))
        self.assertEqual((source / 'backend/first.sqlite3').read_bytes(), b'previous database')
