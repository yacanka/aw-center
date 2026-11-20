"""Desktop profile selection, activation and successful-start persistence."""
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.manager import desktop_startup, preferences


class StartupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve() / 'preferences'
        self.controller = Mock(closing=False, closed=False, tasks={})
        self.states = self.controller.view.task_states.profiles = {}
        self.current = self.controller.view.variables = {'profile': Mock()}
        self.current['profile'].get.return_value = 'dev'
        self.controller.view.form_values.return_value = {'profile': 'dev'}
        self.owner = Mock()
        self.owner.poll.return_value = None

    def startup(self, values=None):
        result = desktop_startup.DesktopStartup(self.controller, self.owner, self.directory, values or {})
        self.addCleanup(result.writer.shutdown)
        return result

    def test_settings_then_secondary_open_uses_successful_profile(self):
        startup = self.startup({'_startup_profile': 'prod', 'profile': 'dev'})
        startup.start(settings=True)
        self.controller.root.after_idle.call_args.args[0]()
        self.controller.show_settings.assert_called_once()
        self.controller.desktop_open.assert_not_called()
        self.owner.poll.return_value = 'open'
        startup.poll()
        self.controller.desktop_open.assert_called_once_with('prod')
        self.controller.inspect_selected.assert_not_called()

    def test_secondary_activation_during_manually_started_first_installation_reuses_its_progress(self):
        self.controller.tasks['a'] = SimpleNamespace(active=True, action='ensure', values={'profile': 'prod'})
        startup = self.startup()
        startup.open()
        self.controller.desktop_open.assert_called_once_with('prod')
        self.controller.inspect_selected.assert_not_called()

    @patch.object(desktop_startup, 'ProfileChooser')
    def test_one_valid_profile_is_opened_after_both_inspections_finish(self, chooser):
        startup = self.startup({'profile': 'dev'})
        startup.open()
        self.controller.inspect_selected.assert_called_once_with('prod')
        self.controller.tasks = {'inspect': SimpleNamespace(active=True, action='inspect')}
        startup.poll()
        self.controller.desktop_open.assert_not_called()
        self.states.update(dev={'status': 'incomplete'}, prod={'status': 'stopped'})
        self.controller.tasks.clear()
        startup.poll()
        chooser.return_value.offer_profiles.assert_not_called()
        self.controller.desktop_open.assert_called_once_with('prod')

    @patch.object(desktop_startup, 'ProfileChooser')
    def test_inconclusive_or_multiple_profiles_require_choice_and_cancel_preserves_preferences(self, chooser):
        for state in ({}, {'dev': {'status': 'stopped'}, 'prod': {'status': 'unverified'}}):
            with self.subTest(state=state):
                startup = self.startup({'profile': 'dev'})
                self.states.update(state)
                startup.open()
                startup.poll()
                self.assertIsNotNone(startup.chooser)
                startup.open()
                chooser.return_value.window.lift.assert_called()
                chooser.call_args.args[2]()
                startup.finish()
                self.assertNotIn('_startup_profile', preferences.load_preferences(self.directory))
        self.controller.desktop_open.assert_not_called()

    @patch.object(desktop_startup, 'ProfileChooser')
    def test_production_waits_for_required_settings_but_dev_starts_at_selection(self, chooser):
        for profile in ('prod', 'dev'):
            startup = self.startup()
            self.states.update(dev={'status': 'not_installed'}, prod={'status': 'not_installed'})
            startup.open()
            startup.poll()
            chooser.call_args.args[1](profile)
            if profile == 'prod':
                self.current['profile'].set.assert_called_once_with('prod')
                self.controller.show_window.assert_called_once()
                startup.open()
                self.controller.desktop_open.assert_not_called()
            else:
                self.controller.desktop_open.assert_called_once_with('dev')

    @patch.object(desktop_startup, 'ProfileChooser')
    def test_settings_signal_during_chooser_cancels_automatic_action(self, chooser):
        startup = self.startup()
        startup.open()
        startup.poll()
        self.owner.poll.return_value = 'settings'
        startup.poll()
        chooser.return_value.window.destroy.assert_called_once()
        self.controller.show_settings.assert_called_once()
        self.controller.desktop_open.assert_not_called()

    @patch('scripts.manager.desktop.create_desktop_shortcut', return_value=True)
    def test_success_is_saved_before_close_and_shortcut_is_created_only_once(self, shortcut):
        startup = self.startup()
        startup.ready('prod')
        startup.writer.submit(lambda: None).result(timeout=5)
        self.assertEqual(preferences.load_preferences(self.directory),
                         {'profile': 'dev', '_startup_profile': 'prod', '_shortcut_created': True})
        startup.ready('prod')
        startup.finish()
        shortcut.assert_called_once_with()
        self.assertEqual(preferences.load_preferences(self.directory)['_startup_profile'], 'prod')

    @patch('scripts.manager.desktop.create_desktop_shortcut', return_value=False)
    def test_failed_shortcut_is_retried_on_next_launch(self, shortcut):
        startup = self.startup()
        startup.ready('dev')
        startup.finish()
        restored = preferences.load_preferences(self.directory)
        self.assertEqual(restored['_startup_profile'], 'dev')
        self.assertNotIn('_shortcut_created', restored)
        restarted = self.startup(restored)
        restarted.ready('dev')
        restarted.finish()
        self.assertEqual(shortcut.call_count, 2)

    def test_invalid_desktop_metadata_is_discarded(self):
        preferences.save_preferences(self.directory, {'_startup_profile': ['prod'], '_shortcut_created': 'yes'})
        self.assertEqual(preferences.load_preferences(self.directory), {})


class ChooserTkTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest('Tk runtime unavailable')
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('Tk display unavailable')
        self.addCleanup(self.root.destroy)

    def test_chooser_is_visible_and_keyboard_accessible_while_root_withdrawn(self):
        root = self.root
        selected = []
        chooser = desktop_startup.ProfileChooser(root, selected.append, root.destroy)
        root.withdraw()
        root.update()
        self.assertEqual(root.state(), 'withdrawn')
        self.assertTrue(chooser.window.winfo_viewable())
        self.assertEqual(root.grab_current(), chooser.window)
        buttons = chooser.window.winfo_children()[0].children
        self.assertEqual(buttons['dev'].cget('text'), 'Bu bilgisayarda kullan')
        self.assertEqual(buttons['prod'].cget('text'), 'Ekibim için sunucu kur')
        buttons['dev'].invoke()
        self.assertEqual(selected, ['dev'])

    def test_new_team_server_displays_only_required_configuration_without_starting(self):
        from scripts.manager.controller import ManagerController
        from scripts.manager.view import ManagerWindow

        class EmptyProfileSession:
            def __init__(self, emit):
                self.emit = emit

            def run(self, request):
                self.emit({'type': 'profile', 'profile': request['profile'], 'status': 'not_installed'})
                self.emit({'type': 'done', 'ok': True})

            def stop(self):
                pass

        def wait_for(predicate):
            deadline = time.monotonic() + 5
            while not predicate() and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.01)
            self.assertTrue(predicate())

        controller = ManagerController(self.root, ManagerWindow, Path.cwd(), session_factory=EmptyProfileSession)
        owner = Mock()
        owner.poll.return_value = None
        startup = desktop_startup.DesktopStartup(controller, owner, None, {})
        self.addCleanup(startup.writer.shutdown)
        startup.start(settings=False)
        wait_for(lambda: startup.chooser is not None and not startup.discovering)
        startup.chooser.window.winfo_children()[0].children['prod'].invoke()
        fields = controller.view._fields
        wait_for(lambda: fields['tls_cert_file'].winfo_viewable())
        for key in ('host', 'tls_cert_file', 'tls_key_file'):
            self.assertTrue(fields[key].winfo_viewable(), key)
        for key in ('backend_port', 'source_root', 'env_file', 'python_command'):
            self.assertFalse(fields[key].winfo_viewable(), key)
        self.assertEqual({task.action for task in controller.tasks.values()}, {'inspect'})
