"""Coordinate desktop launch intent with the existing profile workers and Tk form."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from queue import Empty, SimpleQueue

from . import preferences


class ProfileChooser:
    def __init__(self, root, select, cancel, *, checking=False):
        import tkinter as tk
        from tkinter import ttk

        self.window = tk.Toplevel(root, name='profile_chooser')
        self.window.title('AW Center')
        self.window.resizable(False, False)
        body = ttk.Frame(self.window, padding=24)
        body.grid()
        self.question = ttk.Label(body, text='Kayıtlı kurulumlar denetleniyor…')
        self.question.grid(sticky='w', pady=(0, 14))
        self.buttons = []
        for profile, label in (('dev', 'Bu bilgisayarda kullan'), ('prod', 'Ekibim için sunucu kur')):
            button = ttk.Button(body, name=profile, text=label, command=lambda choice=profile: select(choice))
            button.grid(sticky='ew', pady=4)
            self.buttons.append(button)
            button.grid_remove()
        if not checking:
            self.offer_profiles()
        self.window.protocol('WM_DELETE_WINDOW', cancel)
        self.window.bind('<Escape>', lambda _event: cancel())
        self.window.grab_set()
        self.window.lift()

    def offer_profiles(self):
        self.question.configure(text='AW Center’ı nasıl kullanacaksınız?')
        for button in self.buttons:
            button.grid()
        self.buttons[0].focus_set()


class DesktopStartup:
    """All form access happens on Tk. Private preference writes stay ordered."""

    def __init__(self, controller, owner, directory, initial_values):
        self.controller = controller
        self.root = controller.root
        self.owner = owner
        self.directory = directory
        self.metadata = {key: initial_values[key] for key in ('_contexts', '_media_context', '_startup_profile')
                         if key in initial_values}
        self.shortcut_created = initial_values.get('_shortcut_created') is True
        self.writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix='awcenter-preferences')
        self.warnings = SimpleQueue()
        self.chooser = None
        self.discovering = False
        self.selected = None
        self.production_form = False
        controller.on_desktop_ready = self.ready

    def start(self, settings):
        self.root.after_idle(self.settings if settings else self.open)
        self.root.after(100, self.poll)

    def settings(self):
        self.discovering = False
        self._dismiss_chooser()
        self.controller.show_settings()

    def open(self):
        if self.chooser:
            self.chooser.window.lift()
            return
        profile = self.selected or self.metadata.get('_startup_profile')
        if not profile:
            profile = next((task.values['profile'] for task in reversed(list(self.controller.tasks.values()))
                            if task.active and task.action in {'ensure', 'provision', 'start'}), None)
        if profile:
            if self.production_form:
                self._show_production_form()
            else:
                self.controller.desktop_open(profile)
            return
        # Inspection is read-only and goes through the same contained workers
        # as the settings screen. The controller already inspects the visible profile.
        current = self.controller.view.variables['profile'].get()
        self.discovering = True
        self.chooser = ProfileChooser(self.root, self._choose, self._cancel, checking=True)
        self.root.withdraw()
        self.controller.inspect_selected('prod' if current == 'dev' else 'dev')

    def _choose(self, profile):
        self._dismiss_chooser()
        self.selected = profile
        status = self.controller.view.task_states.profiles.get(profile, {}).get('status')
        if profile == 'prod' and status not in {'stopped', 'unverified'}:
            # New production needs the existing IPv4 and TLS controls before ensure.
            self.production_form = True
            self._show_production_form()
            return
        self.controller.desktop_open(profile)

    def _show_production_form(self):
        view = self.controller.view
        variable = view.variables['profile']
        if variable.get() != 'prod':
            variable.set('prod')
        view.tabs.select(view.run_tab)
        self.controller.show_window()

    def _dismiss_chooser(self):
        if self.chooser:
            self.chooser.window.destroy()
            self.chooser = None

    def _cancel(self):
        self.discovering = False
        self._dismiss_chooser()
        self.controller.show_window()
        self.controller.close()

    def _finish_discovery(self):
        if not self.chooser:
            self.discovering = False
            return
        states = self.controller.view.task_states.profiles
        if any(task.active and task.action == 'inspect' for task in self.controller.tasks.values()):
            return
        self.discovering = False
        valid = [name for name in ('dev', 'prod')
                 if states.get(name, {}).get('status') in {'stopped', 'unverified'}]
        if len(valid) == 1:
            self._choose(valid[0])
        else:
            self.chooser.offer_profiles()

    def poll(self):
        if self.controller.closing or self.controller.closed:
            return
        try:
            command = self.owner.poll()
            if command == 'settings':
                self.settings()
            elif command == 'open':
                self.open()
            if self.discovering:
                self._finish_discovery()
            try:
                warning = self.warnings.get_nowait()
            except Empty:
                return
            from tkinter import messagebox
            self.controller.show_window()
            messagebox.showwarning('AW Center', warning, parent=self.root)
        finally:
            self.root.after(100, self.poll)

    def ready(self, profile):
        self.discovering = self.production_form = False
        self._dismiss_chooser()
        self.selected = profile
        self.metadata['_startup_profile'] = profile
        self.writer.submit(self._save_ready, self._snapshot())

    def _snapshot(self):
        return {**self.metadata, **self.controller.view.form_values(include_profiles=True)}

    def _save(self, values):
        if self.shortcut_created:
            values['_shortcut_created'] = True
        preferences.save_preferences(self.directory or preferences.preferences_home(), values)

    def _save_ready(self, values):
        from .desktop import create_desktop_shortcut
        saved = True
        try:
            self._save(values)
        except preferences.PreferencesError as error:
            saved = False
            self.warnings.put(error.message('save'))
        if self.shortcut_created:
            return
        if create_desktop_shortcut():
            self.shortcut_created = True
            if not saved:
                return
            try:
                self._save(values)
            except preferences.PreferencesError as error:
                self.warnings.put(error.message('save'))
        elif os.name == 'nt':
            self.warnings.put('Masaüstünde AW Center kısayolu oluşturulamadı. Uygulamayı yeniden '
                              'açmak için paketteki AWCenterManager.exe veya kaynak dizinindeki '
                              'AWCenterManager.pyw dosyasına çift tıklayın.')

    def finish(self):
        self.writer.shutdown(wait=True)
        self._save(self._snapshot())
