"""Startup evidence and callback-failure gating without a desktop dependency."""
from __future__ import annotations

from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.manager import main


class ManagerSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.result_path = Path(self.temporary.name) / 'startup.json'
        self.root = Mock()
        self.root.winfo_viewable.return_value = True
        self.root.winfo_width.return_value = 1000
        self.root.winfo_height.return_value = 820
        self.root.tk.call.side_effect = lambda *args: {
            ('package', 'provide', 'Tk'): '8.6.14', ('tk', 'scaling'): 1.5,
        }[args]
        self.style = Mock()
        self.style.theme_use.return_value = 'clam'
        self.default_font = Mock()
        self.default_font.actual.return_value = {'family': 'Segoe UI', 'size': 9, 'weight': 'normal'}
        tkinter = ModuleType('tkinter')
        tkinter.Tk = Mock(return_value=self.root)
        tkinter.ttk = SimpleNamespace(Style=Mock(return_value=self.style))
        tkinter.font = SimpleNamespace(nametofont=Mock(return_value=self.default_font))
        view = ModuleType('scripts.manager.view')
        view.ManagerWindow = Mock()
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.dict('sys.modules', {'tkinter': tkinter, 'scripts.manager.view': view}))
        self.patches.enter_context(patch.object(main, '_dpi_awareness'))
        self.controller_factory = self.patches.enter_context(patch('scripts.manager.controller.ManagerController'))
        self.callbacks = []
        self.root.after.side_effect = lambda _delay, callback: self.callbacks.append(callback)
        self.root.mainloop.side_effect = lambda: self.callbacks.pop()()

    def test_normal_restart_loads_inputs_and_saves_latest_form_on_close(self):
        preferences = importlib.import_module('scripts.manager.preferences')
        self.root.mainloop.side_effect = None
        view = self.controller_factory.return_value.view
        view.form_values.return_value = {'profile': 'dev', 'python_command': 'python'}
        with patch.object(preferences, 'load_preferences', return_value={
                'source_root': 'C:/saved/source', 'python_command': 'py -3.11'}), \
             patch.object(preferences, 'save_preferences') as save, \
             patch.object(preferences, 'preferences_home', return_value=Path('/private/manager')):
            self.assertEqual(main.main([]), 0)
        self.assertEqual(self.controller_factory.call_args.args[2], Path('C:/saved/source'))
        factory = self.controller_factory.call_args.args[1]
        self.assertEqual(factory.keywords['initial_values']['python_command'], 'py -3.11')
        save.assert_called_once_with(Path('/private/manager'), {'profile': 'dev', 'python_command': 'python'})

    def test_explicit_root_overrides_remembered_source(self):
        preferences = importlib.import_module('scripts.manager.preferences')
        self.root.mainloop.side_effect = None
        self.controller_factory.return_value.view.form_values.return_value = {}
        with patch.object(preferences, 'load_preferences', return_value={'source_root': 'C:/saved'}), \
             patch.object(preferences, 'save_preferences'), \
             patch.object(preferences, 'preferences_home', return_value=Path('/private/manager')):
            self.assertEqual(main.main(['--root', 'C:/explicit']), 0)
        self.assertEqual(self.controller_factory.call_args.args[2], Path('C:/explicit'))

    def test_load_failure_shows_safe_detailed_status_and_still_saves_on_close(self):
        preferences = importlib.import_module('scripts.manager.preferences')
        self.root.mainloop.side_effect = None
        error = preferences.PreferencesError('decode', 'invalid_format', legacy=True)
        self.controller_factory.return_value.view.form_values.return_value = {'python_command': 'python'}
        with patch.object(preferences, 'preferences_home', return_value=Path('/private/manager')), \
             patch.object(preferences, 'load_preferences', side_effect=error), \
             patch.object(preferences, 'save_preferences') as save:
            self.assertEqual(main.main([]), 0)
        event = self.controller_factory.return_value.view.handle_event.call_args.args[0]
        self.assertEqual(event['message'], error.message('load'))
        save.assert_called_once_with(Path('/private/manager'), {'python_command': 'python'})

    def test_save_failure_displays_details_instead_of_startup_error(self):
        preferences = importlib.import_module('scripts.manager.preferences')
        self.root.mainloop.side_effect = None
        error = preferences.PreferencesError('replace', 'file_locked')
        with patch.object(preferences, 'preferences_home', return_value=Path('/private/manager')), \
             patch.object(preferences, 'load_preferences', return_value={}), \
             patch.object(preferences, 'save_preferences', side_effect=error), \
             patch.object(main, '_preferences_warning') as warning, patch.object(main, '_startup_error') as startup:
            self.assertEqual(main.main([]), 0)
        warning.assert_called_once_with(error)
        startup.assert_not_called()

    def test_real_user_preferences_survive_close_and_reopen(self):
        self.root.mainloop.side_effect = None
        directory = Path(self.temporary.name).resolve()
        values = {'profile': 'dev', 'python_command': 'python', 'source_root': 'C:/source', 'migrate': True}
        self.controller_factory.return_value.view.form_values.return_value = values
        with patch.dict(os.environ, {'LOCALAPPDATA': str(directory)}):
            self.assertEqual(main.main([]), 0)
            self.assertEqual(main.main([]), 0)
        restored = self.controller_factory.call_args.args[1].keywords['initial_values']
        self.assertEqual(restored['python_command'], 'python')
        self.assertFalse(restored.get('migrate', False))
        self.assertTrue((directory / 'AWCenterManager/manager.json').is_file())
        self.assertFalse((directory / 'AWCenter').exists())

    def run_smoke(self):
        status = main.main(['--smoke-test', str(self.result_path)])
        return status, json.loads(self.result_path.read_text(encoding='utf-8'))

    def test_visible_window_reports_actual_non_sensitive_runtime_metadata(self):
        status, result = self.run_smoke()
        self.assertEqual(status, 0)
        self.assertEqual(result, {
            'schema': 'awcenter.manager.ui-smoke', 'version': 1, 'ready': True,
            'client_size': {'width': 1000, 'height': 820}, 'tk_version': '8.6.14',
            'theme': 'clam', 'scaling': 1.5,
            'default_font': {'family': 'Segoe UI', 'size': 9}, 'callback_error_count': 0,
        })

    def test_callback_error_fails_smoke_even_when_window_is_visible(self):
        def event_loop():
            self.root.report_callback_exception(RuntimeError, RuntimeError('private-operator-value'), None)
            self.callbacks.pop()()
        self.root.mainloop.side_effect = event_loop
        status, result = self.run_smoke()
        self.assertEqual(status, 1)
        self.assertIs(result['ready'], False)
        self.assertEqual(result['callback_error_count'], 1)
        self.assertNotIn('private-operator-value', self.result_path.read_text(encoding='utf-8'))

    def test_non_viewable_window_fails_smoke(self):
        self.root.winfo_viewable.return_value = False
        status, result = self.run_smoke()
        self.assertEqual(status, 1)
        self.assertIs(result['ready'], False)

    def test_smoke_callback_failure_still_writes_failed_evidence(self):
        self.default_font.actual.side_effect = RuntimeError('private-metadata-value')
        def event_loop():
            try:
                self.callbacks.pop()()
            except RuntimeError as error:
                self.root.report_callback_exception(RuntimeError, error, None)
        self.root.mainloop.side_effect = event_loop
        status = main.main(['--smoke-test', str(self.result_path)])
        self.assertEqual(status, 1)
        self.assertTrue(self.result_path.is_file(), 'Callback failure must retain startup evidence')
        result = json.loads(self.result_path.read_text(encoding='utf-8'))
        self.assertIs(result['ready'], False)
        self.assertEqual(result['callback_error_count'], 1)
        self.assertNotIn('private-metadata-value', self.result_path.read_text(encoding='utf-8'))

    def test_startup_failure_still_writes_versioned_evidence_without_exception_details(self):
        self.root.mainloop.side_effect = RuntimeError('private-startup-value')
        status, result = self.run_smoke()
        self.assertEqual(status, 1)
        self.assertIs(result['ready'], False)
        self.assertEqual(result.get('schema'), 'awcenter.manager.ui-smoke')
        self.assertEqual(result.get('version'), 1)
        self.assertEqual(result.get('callback_error_count'), 0)
        self.assertNotIn('private-startup-value', self.result_path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
