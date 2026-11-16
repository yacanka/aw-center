"""Connection overrides remain raw global inputs across source selections."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.manager import paths, preferences
from scripts.manager.view_model import FormError, normalize_values


class GlobalInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.media = []
        for name in ('first', 'second'):
            directory = self.root / name
            directory.mkdir()
            (directory / 'manager-manifest.json').write_text(json.dumps({
                'format_version': 2, 'complete': True, 'source_fingerprint': name,
            }), encoding='utf-8')
            self.media.append(directory)

    def startup(self, media, saved):
        with patch.object(paths.sys, 'frozen', True, create=True), \
             patch.object(paths.sys, 'executable', str(media / 'AWCenterManager.exe')):
            return paths.startup_values(saved, None)

    def test_new_media_keeps_connection_inputs_while_resetting_source_paths(self):
        selected = {**self.startup(self.media[0], {}),
                    'host': '192.0.2.20', 'backend_port': '18000', 'frontend_port': '15173',
                    'python_command': 'C:/first/python.exe', 'env_file': 'C:/first/app.env'}

        moved = self.startup(self.media[1], selected)

        self.assertEqual(moved['host'], '192.0.2.20')
        self.assertEqual(moved['backend_port'], '18000')
        self.assertEqual(moved['frontend_port'], '15173')
        self.assertEqual(moved['python_command'], '')
        self.assertEqual(moved['env_file'], '')
        self.assertEqual(moved['source_root'], str(self.media[1] / 'source'))

    def test_returning_media_cannot_restore_old_connection_inputs(self):
        selected = {**self.startup(self.media[0], {}),
                    'host': '192.0.2.20', 'backend_port': '18000', 'frontend_port': '15173',
                    'python_command': 'C:/first/python.exe', 'env_file': 'C:/first/app.env'}
        moved = self.startup(self.media[1], selected)
        for current in ({'host': 'localhost', 'backend_port': '18001', 'frontend_port': '15174'},
                        {'host': '', 'backend_port': '', 'frontend_port': ''}):
            with self.subTest(current=current):
                restored = self.startup(self.media[0], {**moved, **current})
                self.assertEqual(restored['host'], current['host'])
                self.assertEqual(restored['backend_port'], current['backend_port'])
                self.assertEqual(restored['frontend_port'], current['frontend_port'])
                self.assertEqual(restored['python_command'], 'C:/first/python.exe')
                self.assertEqual(restored['env_file'], 'C:/first/app.env')

    def test_env_switch_and_restart_preserve_raw_and_cleared_inputs(self):
        home = self.root / 'preferences'
        saved = self.startup(self.media[0], {})
        for name, host, backend_port, frontend_port in (
            ('first.env', '192.0.2.20', '18000', '15173'),
            ('second.env', '192.0.2.20', '18000', '15173'),
            ('second.env', '', '', ''),
        ):
            with self.subTest(name=name, host=host):
                environment = self.root / name
                original = b'HOST=192.0.2.50\nBACKEND_PORT=18050\n'
                environment.write_bytes(original)
                saved.update(env_file=str(environment), host=host, backend_port=backend_port,
                             frontend_port=frontend_port)
                preferences.save_preferences(home, saved)
                saved = self.startup(self.media[0], preferences.load_preferences(home))
                self.assertEqual(saved['env_file'], str(environment))
                self.assertEqual(saved['host'], host)
                self.assertEqual(saved['backend_port'], backend_port)
                self.assertEqual(saved['frontend_port'], frontend_port)
                self.assertEqual(environment.read_bytes(), original)


class LocalHostInputTests(unittest.TestCase):
    def test_explicit_ipv4_and_localhost_are_valid_without_replacing_blank_inputs(self):
        for action in ('provision', 'ensure'):
            for host in ('', '127.0.0.1', 'localhost', '192.0.2.20', '0.0.0.0'):
                with self.subTest(action=action, host=host):
                    values = normalize_values(action, {'host': host})
                    self.assertEqual(values['host'], host)
                    self.assertEqual(values['backend_port'], '')
                    self.assertEqual(values['frontend_port'], '')

    def test_invalid_local_bindings_identify_the_field_without_echoing_input(self):
        for host in ('https://private.invalid', 'private.invalid', '::1', '999.0.0.1',
                     '224.0.0.1', '255.255.255.255', '127.0.0.1\nprivate'):
            with self.subTest(host=host), self.assertRaises(FormError) as caught:
                normalize_values('ensure', {'host': host})
            self.assertEqual(caught.exception.field, 'host')
            self.assertNotIn(host, str(caught.exception))

    def test_production_restrictions_remain_in_force(self):
        for host in ('localhost', '127.0.0.1', '0.0.0.0', '224.0.0.1'):
            with self.subTest(host=host), self.assertRaises(FormError) as caught:
                normalize_values('ensure', {'profile': 'prod', 'host': host})
            self.assertEqual(caught.exception.field, 'host')
