"""The desktop profile form remembers manual inputs independently of ENV overlays."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.manager import preferences


class ProfileStorageTests(unittest.TestCase):
    def test_nested_drafts_only_keep_supported_non_secret_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'preferences'
            preferences.save_preferences(home, {
                '_last_form': 'prod', '_profile_forms': {
                    'dev': {'host': 'localhost', 'live_reload': False},
                    'prod': {'host': '192.0.2.1', 'deploy_check': True, 'SECRET_KEY': 'hidden',
                             'python_index_url': 'https://secret@example.invalid/', 'python_command': 'python.exe'},
                }})
            record = preferences.load_preferences(home)
            self.assertEqual(record.get('_last_form'), 'prod')
            self.assertEqual(record['_profile_forms']['dev'], {'host': 'localhost', 'live_reload': False})
            self.assertEqual(record['_profile_forms']['prod'], {'host': '192.0.2.1', 'deploy_check': True,
                                                                'python_command': 'python.exe'})
            self.assertNotIn('hidden', (home / 'manager.json').read_text())


class ProfileWindowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from scripts.manager import profile_window

        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('Tk display unavailable')
        self.addCleanup(self.root.destroy)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name)
        self.home = self.source / 'prefs'
        home = patch.object(preferences, 'preferences_home', return_value=self.home)
        home.start()
        self.addCleanup(home.stop)
        discovery = patch.object(profile_window, 'python_choices', return_value=[])
        discovery.start()
        self.addCleanup(discovery.stop)
        run = patch.object(profile_window, 'start_task')
        self.run_task = run.start()
        self.addCleanup(run.stop)
        self.window = profile_window.ProfileWindow(self.root, self.source)

    def test_select_edit_switch_and_reopen_without_starting(self):
        self.assertIsNone(self.window.profile)
        self.window.select('dev')
        self.window.variables['backend_port'].set('8042')
        self.window.back()
        self.window.select('prod')
        self.assertEqual(self.window.variables['backend_port'].get(), '443')
        self.window.variables['host'].set('192.0.2.55')
        self.window.save()
        record = preferences.load_preferences(self.home)
        self.assertEqual(record['_last_form'], 'prod')
        self.assertEqual(record['_profile_forms']['dev']['backend_port'], '8042')
        self.assertEqual(record['_profile_forms']['prod']['host'], '192.0.2.55')
        self.assertFalse(record['_profile_forms']['prod']['deploy_check'])
        self.run_task.assert_not_called()

    def test_env_overlay_never_replaces_manual_draft(self):
        self.window.select('dev')
        self.window.variables['host'].set('localhost')
        selected = self.source / 'local.env'
        selected.write_text('IPV4_ADDRESS=127.0.0.2\nSECRET_KEY=must-not-persist\n')
        self.window.set_env(str(selected))
        self.assertTrue(self.window.fields['host'].instate(['readonly']))
        self.assertEqual(self.window.variables['host'].get(), '127.0.0.2')
        self.window.save()
        self.assertEqual(preferences.load_preferences(self.home)['_profile_forms']['dev']['host'], 'localhost')
        self.assertNotIn('must-not-persist', (self.home / 'manager.json').read_text())
        self.window.set_env('')
        self.assertFalse(self.window.fields['host'].instate(['readonly']))
        self.assertEqual(self.window.variables['host'].get(), 'localhost')

    def test_duplicate_start_is_blocked_until_cleanup_finishes(self):
        self.window.select('dev')
        self.window.action('run')
        self.window.action('install')
        self.run_task.assert_called_once()
        action, values, notify, _ask = self.run_task.call_args.args
        self.assertEqual((action, values['source_root']), ('run', str(self.source)))
        self.window.stop()
        self.run_task.return_value.stop.assert_called_once()
        notify('error', 'Test')
        self.window.drain()
        self.assertIsNotNone(self.window.task)
        notify('done', '')
        self.window.drain()
        self.assertIsNone(self.window.task)

    def test_resource_mode_exposes_its_fields_and_full_results_survive_completion(self):
        self.window.select('prod')
        for mode in ('online', 'corporate', 'offline'):
            self.window.variables['source_mode'].set(mode)
            self.window._resource_mode()
            for key, group in self.window.resource_groups.items():
                self.assertEqual(bool(group.grid_info()), mode == key)
        self.window.action('check')
        _, values, notify, _ask = self.run_task.call_args.args
        self.assertEqual(values['source_mode'], 'offline')
        message = ', '.join('package-%d==1.0' % i for i in range(1500))
        notify('status', message)
        notify('done', 'Tamamlandı.')
        self.window.drain()
        self.assertIn('package-1499==1.0', self.window.log.get('1.0', 'end'))
        self.assertEqual(self.window.status.get(), 'Tamamlandı.')

    def test_saved_form_opens_without_writing_or_starting(self):
        import tkinter as tk
        from scripts.manager.profile_window import ProfileWindow

        self.window.select('prod')
        self.window.variables['backend_port'].set('9443')
        self.window.save()
        dialog = tk.Toplevel(self.root)
        self.addCleanup(dialog.destroy)
        with patch.object(preferences, 'save_preferences') as write:
            restored = ProfileWindow(dialog, self.source)
        write.assert_not_called()
        self.assertEqual(restored.profile, 'prod')
        self.assertEqual(restored.variables['backend_port'].get(), '9443')
        self.run_task.assert_not_called()

    def test_lan_default_keeps_manual_or_env_address(self):
        self.window.select('prod')
        self.window.variables['host'].set('192.0.2.22')
        self.window.events.put(('lan', '192.0.2.11'))
        self.window.drain()
        self.assertEqual(self.window.variables['host'].get(), '192.0.2.22')
