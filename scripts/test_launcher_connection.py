"""Automatic ports and journaled bind changes preserve private profile state."""
import json
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import test_launcher_profiles as fixtures
from scripts.launcher import installation_profiles as profiles
from scripts.launcher.model import LauncherError


class ConnectionTests(unittest.TestCase):
    setUp = fixtures.ProfileTests.setUp
    provision = fixtures.ProfileTests.provision

    def test_loopback_selection_cannot_reallocate_production(self):
        from scripts.launcher.installation_connection import select_ports
        with (patch('scripts.launcher.installation_connection.socket.socket', side_effect=AssertionError('Must not probe prod')),
              self.assertRaises(LauncherError)):
            select_ports({'name': 'prod'}, {})

    def test_connection_journal_recovers_before_environment_publication(self):
        from scripts.launcher.installation_connection import update_connection
        profile = self.provision()
        original = profiles.read_profile_environment(profile)
        with patch.object(profiles, '_write_replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                update_connection(self.project, profile, {'frontend_port': 15173})
        recovered = self.provision()
        self.assertEqual(recovered['frontend_port'], 15173)
        self.assertEqual(profiles.read_profile_environment(recovered)['SECRET_KEY'], original['SECRET_KEY'])

    def test_occupied_automatic_port_changes_but_manual_port_fails(self):
        from scripts.launcher.installation_connection import select_ports
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            occupied = listener.getsockname()[1]
            result = select_ports(None, {'backend_port': occupied}, automatic={'backend_port'})
            self.assertNotEqual(result['backend_port'], occupied)
            self.assertNotEqual(result['backend_port'], result['frontend_port'])
            self.assertEqual(result['port_modes']['backend_port'], 'automatic')
            with self.assertRaises(LauncherError):
                select_ports(None, {'backend_port': occupied})

    def test_legacy_port_is_fixed_even_when_form_is_blank(self):
        from scripts.launcher.installation_connection import select_ports
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            profile = self.provision(backend_port=listener.getsockname()[1])
            with self.assertRaises(LauncherError):
                select_ports(profile, {})

    def test_connection_change_preserves_secrets_and_updates_generated_urls(self):
        from scripts.launcher.installation_connection import update_connection
        before = self.provision()
        original = profiles.read_profile_environment(before)
        after = update_connection(self.project, before, {'backend_port': 18000, 'frontend_port': 15173,
                                  'port_modes': {'backend_port': 'automatic', 'frontend_port': 'manual'}})
        values = profiles.read_profile_environment(after)
        self.assertEqual(values['FRONTEND_RESET_URL'], 'http://127.0.0.1:15173/app/login')
        self.assertIn('http://localhost:18000', values['CSRF_TRUSTED_ORIGINS'])
        for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY', 'DATABASE_URL', 'PRIVATE_MEDIA_ROOT'):
            self.assertEqual(values[key], original[key])
        self.assertEqual(profiles.load_profile(self.project, 'dev', self.home)['backend_port'], 18000)

    def test_custom_derived_url_blocks_rebind_without_partial_changes(self):
        from scripts.launcher.installation_connection import update_connection
        profile = self.provision()
        env = Path(profile['env_file'])
        values = profiles.read_profile_environment(profile)
        values['FRONTEND_RESET_URL'] = 'https://custom.example/app/login'
        profiles._write_replace(env, profiles._environment_content(values))
        before = env.read_bytes()
        with self.assertRaises(LauncherError):
            update_connection(self.project, profile, {'frontend_port': 15173})
        self.assertEqual(env.read_bytes(), before)
        self.assertEqual(profiles.load_profile(self.project, 'dev', self.home)['frontend_port'], 5173)

    def test_interrupted_connection_publish_recovers_same_keys(self):
        from scripts.launcher.installation_connection import update_connection
        profile = self.provision()
        original = profiles.read_profile_environment(profile)
        write = profiles._write_replace
        def interrupt(path, content):
            if path.name == 'dev.profile.json':
                raise OSError('simulated interruption')
            write(path, content)
        with patch.object(profiles, '_write_replace', side_effect=interrupt):
            with self.assertRaises(OSError):
                update_connection(self.project, profile, {'frontend_port': 15173})
        recovered = self.provision()
        self.assertEqual(recovered['frontend_port'], 15173)
        self.assertEqual(profiles.read_profile_environment(recovered)['SECRET_KEY'], original['SECRET_KEY'])
        self.assertFalse((self.home / 'config/dev.pending.json').exists())

    def test_port_provenance_rejects_unknown_values(self):
        profile = self.provision()
        path = self.home / 'config/dev.profile.json'
        profile['port_modes'] = {'backend_port': 'invalid', 'frontend_port': 'automatic'}
        profiles._write_replace(path, json.dumps(profile))
        with self.assertRaises(LauncherError):
            profiles.load_profile(self.project, 'dev', self.home)
