"""Profile-first desktop UI. Workers communicate with Tk only through the event queue."""
from __future__ import annotations

import ipaddress
from pathlib import Path
from queue import Empty, Queue, SimpleQueue
import socket
import threading
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
import webbrowser

from scripts.launcher.installation_profiles import installation_home
from scripts.launcher.model import LauncherError
from . import preferences
from .profile_resources import python_choices
from .profile_runtime import env_fields
from .profile_tasks import start_task
from .view_model import FormError, _ready_url, safe_text, validate_admin


PROFILES = {'dev': 'Local', 'prod': 'Prod'}
CHECKS = (
    ('deploy_check', 'Django dağıtım kontrolü (check --deploy)'),
    ('migration_check', 'Bekleyen migration kontrolü'),
    ('collectstatic', 'Statik dosyaları topla (collectstatic)'),
    ('verify_frontend', 'Frontend build çıktısını doğrula'),
)


def _profile_drafts(saved):
    forms = {}
    for name in PROFILES:
        values = dict(preferences.PROFILE_FORM_DEFAULTS)
        values.update(host='127.0.0.1' if name == 'dev' else '',
                      backend_port='8000' if name == 'dev' else '443', frontend_port='5173')
        if name == 'prod':
            try:
                tls = installation_home() / 'tls' / 'prod'
                values.update(tls_cert_file=str(tls / 'server.crt'), tls_key_file=str(tls / 'server.key'))
            except LauncherError:
                pass
        if '_profile_forms' in saved:
            values.update(saved['_profile_forms'].get(name, {}))
        else:
            # Older managers kept three fields per profile and the rest on the active form.
            if saved.get('profile') == name:
                values.update({key: saved[key] for key in values if key in saved and saved[key] != ''})
            for key in ('host', 'backend_port', 'env_file'):
                if saved.get(f'{name}_{key}'):
                    values[key] = saved[f'{name}_{key}']
        if values['source_mode'] not in ('corporate', 'offline'):
            values['source_mode'] = 'online'
        forms[name] = values
    return forms


class ProfileWindow:
    def __init__(self, root, source: Path):
        self.root, self.source = root, Path(source)
        self.profile = self.task = self.admin = None
        self.closing = False
        self.stopping = False
        self.ready_url = ''
        self.events = SimpleQueue()
        self.interpreters = []
        self.locked = {}
        self.env_error = ''
        self.fields = {}
        self.variables = {}
        self.status = tk.StringVar(root)
        self.buttons = {}
        self.saved = {}
        try:
            self.saved = preferences.load_preferences(preferences.preferences_home())
        except preferences.PreferencesError as error:
            self.status.set(error.message('load'))
        self.forms = _profile_drafts(self.saved)
        root.title('AW Center Manager')
        root.geometry('760x690')
        root.minsize(520, 500)
        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.title_font = font.nametofont('TkDefaultFont', root=root).copy()
        self.title_font.configure(size=16, weight='bold')
        self.body = ttk.Frame(root, padding=(16, 12))
        self.body.grid(row=0, column=0, sticky='nsew')
        self.body.columnconfigure(0, weight=1)
        self.footer = ttk.Label(root, textvariable=self.status, wraplength=680, padding=(16, 6))
        self.footer.grid(row=1, column=0, sticky='ew')
        self.error_details = ttk.Button(root, text='Hata ayrıntıları', command=self._show_error)
        self.error_details.grid(row=2, column=0, sticky='w', padx=16, pady=(0, 6))
        self.error_details.grid_remove()
        last = self.saved.get('_last_form', self.saved.get('profile'))
        if last in PROFILES:
            self.select(last)
        else:
            self.back()
        self.root.after(75, self._poll)
        threading.Thread(target=self._discover_defaults, daemon=True).start()

    def _discover_defaults(self):
        try:
            addresses = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
            for info in addresses:
                address = ipaddress.IPv4Address(info[4][0])
                if not (address.is_loopback or address.is_unspecified or address.is_multicast):
                    self.events.put(('lan', str(address)))
                    break
        except (OSError, ValueError):
            pass
        try:
            self.events.put(('python', python_choices()))
        except (OSError, LauncherError):
            self.events.put(('python', []))

    def _clear(self):
        self.error_details.grid_remove()
        for child in self.body.winfo_children():
            child.destroy()
        self.fields, self.variables, self.buttons = {}, {}, {}
        self.locked, self.pickers = {}, {}
        self.body.rowconfigure(1, weight=0)
        self.body.rowconfigure(2, weight=0)

    def activate(self, settings=False):
        self.root.deiconify()
        self.root.lift()
        if self.admin:
            self.admin.lift()

    def back(self):
        if self.task:
            return
        if self.profile:
            self.save()
            self.status.set('')
        self.profile = None
        self._clear()
        box = ttk.Frame(self.body, padding=12)
        box.grid(row=0, column=0, sticky='w')
        ttk.Label(box, text='Hangi profili açmak istersiniz?', font=self.title_font).grid(
            row=0, column=0, sticky='w', pady=(16, 18))
        for row, (name, label) in enumerate(PROFILES.items(), start=1):
            button = ttk.Button(box, text=label, width=24, command=lambda p=name: self.select(p))
            self.buttons[name] = button
            button.grid(row=row, column=0, sticky='w', pady=4)
            if row == 1:
                button.focus_set()

    def select(self, profile):
        if profile not in PROFILES or self.task:
            return
        if self.profile:
            self.save()
        self._clear()
        self.profile = profile
        self.saved['_last_form'] = profile
        self.variables = {
            key: (tk.BooleanVar if isinstance(value, bool) else tk.StringVar)(self.root, value=value)
            for key, value in self.forms[profile].items()}
        header = ttk.Frame(self.body)
        header.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=PROFILES[profile], font=self.title_font).grid(row=0, column=0, sticky='w')
        self.buttons['back'] = ttk.Button(header, text='Geri', command=self.back)
        self.buttons['back'].grid(row=0, column=1, sticky='e')
        tabs = ttk.Notebook(self.body)
        tabs.grid(row=1, column=0, sticky='nsew')
        self.body.rowconfigure(1, weight=1)
        server = ttk.Frame(tabs, padding=(12, 10))
        server.columnconfigure(1, weight=1)
        tabs.add(server, text='Sunucu')
        resources = ttk.Frame(tabs, padding=(12, 10))
        resources.columnconfigure(1, weight=1)
        tabs.add(resources, text='Kaynaklar')
        self._server(server)
        self._resources(resources)
        controls = ttk.Frame(self.body)
        controls.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        self._button(controls, 'run', 'Çalıştır', 0)
        self.buttons['stop'] = ttk.Button(controls, text='Durdur', command=self.stop)
        self.buttons['stop'].grid(row=0, column=1, padx=(6, 0))
        self.buttons['browser'] = ttk.Button(controls, text='Tarayıcıda aç', command=self._browser)
        self.buttons['browser'].grid(row=0, column=2, padx=(6, 0))
        self._show_python()
        self.set_env(self.variables['env_file'].get())
        self._update_buttons()

    def _button(self, parent, key, title, column):
        button = ttk.Button(parent, text=title, command=lambda: self.action(key))
        button.grid(row=0, column=column, padx=(6 if column else 0, 0), sticky='w')
        self.buttons[key] = button

    def _field(self, parent, row, key, title, picker=None):
        ttk.Label(parent, text=title).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=3)
        entry = ttk.Entry(parent, textvariable=self.variables[key], width=20)
        entry.grid(row=row, column=1, sticky='ew', pady=3)
        self.fields[key] = entry
        if picker:
            button = ttk.Button(parent, text='Seç…', command=lambda: self._pick(key, picker))
            button.grid(row=row, column=2, sticky='e', padx=(6, 0))
            self.pickers[key] = button
        return entry

    def _pick(self, key, kind):
        if kind == 'directory':
            selected = filedialog.askdirectory(parent=self.root, mustexist=True)
        else:
            selected = filedialog.askopenfilename(parent=self.root)
        if selected:
            if key == 'env_file':
                self.set_env(selected)
            else:
                self.variables[key].set(selected)
                if key == 'python_command':
                    self._show_python()

    def _server(self, frame):
        ttk.Label(frame, text='Kaynak klasörü').grid(row=0, column=0, sticky='w', padx=(0, 12), pady=3)
        source = ttk.Entry(frame, width=20)
        source.insert(0, str(self.source))
        source.state(['readonly'])
        source.grid(row=0, column=1, columnspan=2, sticky='ew')
        required = ttk.LabelFrame(frame, text='Gerekli ayarlar', padding=(8, 4))
        required.grid(row=1, column=0, columnspan=4, sticky='ew', pady=(6, 4))
        required.columnconfigure(1, weight=1)
        optional = ttk.LabelFrame(frame, text='İsteğe bağlı ayarlar', padding=(8, 4))
        optional.grid(row=2, column=0, columnspan=4, sticky='ew', pady=4)
        optional.columnconfigure(1, weight=1)
        env = self._field(optional, 0, 'env_file', '.env dosyası', 'file')
        for event in ('<FocusOut>', '<Return>'):
            env.bind(event, lambda _: self.set_env(self.variables['env_file'].get()))
        ttk.Button(optional, text='Temizle', command=lambda: self.set_env('')).grid(row=0, column=3, padx=(4, 0))
        self.env_note = tk.StringVar(self.root)
        ttk.Label(optional, textvariable=self.env_note, wraplength=490).grid(
            row=1, column=0, columnspan=4, sticky='w')
        ttk.Checkbutton(optional, text='Bekleyen migration’ları uygula',
                        variable=self.variables['migrate_on_start']).grid(
            row=2, column=0, columnspan=4, sticky='w', pady=3)
        self._field(required, 0, 'host', 'Sunucu adresi' if self.profile == 'dev' else 'Sabit IPv4')
        self._field(required, 1, 'backend_port', 'Backend portu' if self.profile == 'dev' else 'HTTPS portu')
        ttk.Label(required, text='Python').grid(row=3, column=0, sticky='w')
        self.python_label = tk.StringVar(self.root)
        self.python = ttk.Combobox(required, state='readonly', textvariable=self.python_label, width=22)
        self.python.grid(row=3, column=1, sticky='ew', pady=4)
        self.python.bind('<<ComboboxSelected>>', self._python_selected)
        ttk.Button(required, text='Seç…', command=lambda: self._pick('python_command', 'file')).grid(row=3, column=2)
        if self.profile == 'dev':
            self._field(required, 2, 'frontend_port', 'Frontend portu')
            ttk.Checkbutton(optional, text='Canlı yenileme (Django ve Vite)',
                            variable=self.variables['live_reload']).grid(row=3, column=0, columnspan=3, sticky='w', pady=3)
            return
        self._field(required, 4, 'tls_cert_file', 'TLS sertifikası', 'file')
        self._field(required, 5, 'tls_key_file', 'TLS özel anahtarı', 'file')
        operations = ttk.Frame(frame)
        operations.grid(row=3, column=0, columnspan=4, sticky='w', pady=(5, 0))
        self._button(operations, 'tls', 'Bu IP için sertifika oluştur', 0)
        self._button(operations, 'build', 'Frontend’i derle', 1)
        ttk.Label(required, text='TLS dosyalarınız yoksa bu IP için sertifika oluşturabilirsiniz.',
                  wraplength=450).grid(row=6, column=0, columnspan=3, sticky='w')
        self.advanced_open = tk.BooleanVar(self.root, value=False)
        checks = ttk.Frame(optional)
        checks.grid(row=4, column=0, columnspan=4, sticky='w', padx=10)
        for row, (key, title) in enumerate(CHECKS):
            ttk.Checkbutton(checks, text=title, variable=self.variables[key]).grid(row=row, column=0, sticky='w')
        checks.grid_remove()
        ttk.Checkbutton(optional, text='Gelişmiş ayarlar', variable=self.advanced_open,
                        command=lambda: checks.grid() if self.advanced_open.get() else checks.grid_remove()
                        ).grid(row=3, column=0, columnspan=4, sticky='w')

    def _resources(self, frame):
        modes = ttk.Frame(frame)
        modes.grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 8))
        for column, (mode, title) in enumerate((('online', 'Online'), ('corporate', 'Kurumsal'), ('offline', 'Offline'))):
            ttk.Radiobutton(modes, text=title, value=mode, variable=self.variables['source_mode'],
                            command=self._resource_mode).grid(row=0, column=column, padx=(0, 12))
        self.resource_groups = {}
        for mode, entries in (
            ('corporate', (('python_index_url', 'Python indeks URL’si'), ('npm_registry_url', 'npm registry URL’si'))),
            ('offline', (('wheels_dir', 'Python wheel klasörü'), ('npm_cache_dir', 'npm cache klasörü'))),
        ):
            group = ttk.Frame(frame)
            group.grid(row=1, column=0, columnspan=3, sticky='ew')
            group.columnconfigure(1, weight=1)
            self.resource_groups[mode] = group
            for row, (key, title) in enumerate(entries):
                self._field(group, row, key, title, 'directory' if mode == 'offline' else None)
        online = ttk.Label(frame, text='Python paketleri PyPI, frontend paketleri npm üzerinden alınır.')
        online.grid(row=1, column=0, columnspan=3, sticky='w')
        self.resource_groups['online'] = online
        actions = ttk.Frame(frame)
        actions.grid(row=2, column=0, columnspan=3, sticky='w', pady=(14, 4))
        self._button(actions, 'check', 'Eksik paketleri listele', 0)
        self._button(actions, 'install', 'Eksik paketleri kur', 1)
        ttk.Label(frame, text='İşlem çıktısı').grid(row=3, column=0, sticky='w', pady=(10, 4))
        result = ttk.Frame(frame)
        result.grid(row=4, column=0, columnspan=3, sticky='nsew')
        frame.rowconfigure(4, weight=1)
        result.rowconfigure(0, weight=1)
        result.columnconfigure(0, weight=1)
        self.log = tk.Text(result, height=6, width=30, wrap='word', state='disabled')
        scrollbar = ttk.Scrollbar(result, orient='vertical', command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        self._resource_mode()

    def _resource_mode(self):
        for mode, group in self.resource_groups.items():
            if mode == self.variables['source_mode'].get():
                group.grid()
            else:
                group.grid_remove()

    def _show_python(self):
        current = self.variables['python_command'].get()
        self.python_options = {'Otomatik (.venv / CPython 3.11)': ''}
        for label, path in self.interpreters:
            self.python_options[label] = str(path)
        selected = next((key for key, value in self.python_options.items() if value == current), current)
        if current and selected == current:
            self.python_options[current] = current
        self.python.configure(values=tuple(self.python_options))
        self.python_label.set(selected)

    def _python_selected(self, _event):
        self.variables['python_command'].set(self.python_options[self.python_label.get()])

    def _capture(self):
        if self.profile:
            self.forms[self.profile].update({key: var.get() for key, var in self.variables.items()
                                             if key not in self.locked})

    def set_env(self, selected):
        self._capture()
        draft = self.forms[self.profile]
        draft['env_file'] = selected.strip()
        self.variables['env_file'].set(draft['env_file'])
        old = self.locked
        self.env_error = ''
        try:
            self.locked = env_fields({**draft, 'profile': self.profile, 'source_root': str(self.source)})
        except (OSError, ValueError, LauncherError):
            self.locked = {}
            self.env_error = 'Seçilen .env okunamadı. Dosya yolunu ve içeriğini kontrol edin.'
        for key in old.keys() | self.locked.keys():
            if key in self.fields:
                self.fields[key].state(['readonly'] if key in self.locked else ['!readonly'])
                if key in self.pickers:
                    self.pickers[key].state(['disabled'] if key in self.locked else ['!disabled'])
                self.variables[key].set(self.locked.get(key, draft[key]))
        self.env_note.set(self.env_error or ('Seçili .env içindeki bağlantı değerleri salt okunur.'
                                              if self.locked else ''))

    def save(self):
        self._capture()
        self.saved['_profile_forms'] = self.forms
        try:
            preferences.save_preferences(preferences.preferences_home(), self.saved)
        except preferences.PreferencesError as error:
            self.status.set(error.message('save'))

    def action(self, action):
        if self.task or not self.profile or self.closing:
            return
        self.set_env(self.variables['env_file'].get())
        if self.env_error and action in ('run', 'tls', 'build'):
            self.status.set(self.env_error)
            return
        self.save()
        # The worker reads ENV at execution. Include only the manual fallback values.
        values = {**self.forms[self.profile], 'source_root': str(self.source), 'profile': self.profile}
        if action == 'tls':
            confirmed = messagebox.askokcancel(
                'TLS sertifikası oluştur',
                'Seçili IPv4 için kendinden imzalı bir sertifika ve özel anahtar oluşturulacak. '
                'Tarayıcının bağlantıya güvenmesi için istemci bilgisayarlarda sertifikaya güven tanımlamanız gerekir.',
                parent=self.root)
            if not confirmed:
                return
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')
        self.status.set('İşlem başlatılıyor…')
        self.error_details.grid_remove()
        self.ready_url = ''
        self.last_error = ''
        try:
            self.task = start_task(action, values, self._notify, self._ask)
        except (OSError, LauncherError):
            self.status.set('İşlem başlatılamadı. Python ve kaynak klasörünü kontrol edin.')
        self._update_buttons()

    def _notify(self, kind, text):
        self.events.put((kind, text))

    def _show_error(self):
        messagebox.showerror('İşlem başarısız', self.last_error, parent=self.root)

    def _ask(self):
        answer = Queue(maxsize=1)
        self.events.put(('admin', answer))
        return answer.get()

    def _prompt_admin(self, answer):
        if self.closing or self.stopping or not self.task:
            answer.put(None)
            return
        dialog = self.admin = tk.Toplevel(self.root)
        dialog.title('İlk yönetici hesabı')
        dialog.transient(self.root)
        box = ttk.Frame(dialog, padding=16)
        box.grid()
        names = ('Kullanıcı adı', 'Parola', 'Parola tekrarı')
        fields = []
        for row, title in enumerate(names):
            ttk.Label(box, text=title).grid(row=row, column=0, sticky='w', padx=(0, 8))
            entry = ttk.Entry(box, show='' if row == 0 else '*')
            entry.grid(row=row, column=1, pady=3)
            fields.append(entry)
        notice = ttk.Label(box, text='Kullanıcı adında bir harf ve beş rakam kullanın.', wraplength=320)
        notice.grid(row=3, column=0, columnspan=2, sticky='w')

        def resolve(value):
            self.admin = None
            dialog.destroy()
            answer.put(value)

        def submit():
            try:
                admin = validate_admin(*(entry.get() for entry in fields))
            except FormError as error:
                notice.configure(text=str(error))
                return
            resolve((admin['username'], admin['password']))

        self.cancel_admin = lambda: resolve(None)
        ttk.Button(box, text='İptal', command=self.cancel_admin).grid(row=4, column=0, pady=(8, 0))
        ttk.Button(box, text='Hesap oluştur', command=submit).grid(row=4, column=1, pady=(8, 0))
        dialog.protocol('WM_DELETE_WINDOW', self.cancel_admin)
        dialog.bind('<Return>', lambda _: submit())
        dialog.bind('<Escape>', lambda _: self.cancel_admin())
        dialog.grab_set()
        fields[0].focus_set()

    def _update_buttons(self):
        for key, button in self.buttons.items():
            enabled = (bool(self.task) if key == 'stop' else bool(self.ready_url)
                       if key == 'browser' else not self.task)
            button.state(['!disabled'] if enabled else ['disabled'])

    def stop(self):
        if self.task and not self.stopping:
            self.stopping = True
            if self.admin:
                self.cancel_admin()
            self.task.stop()
            self.status.set('İşlem durduruluyor…')
            self.buttons['stop'].state(['disabled'])

    def _browser(self):
        if self.ready_url:
            try:
                opened = webbrowser.open(self.ready_url)
            except (OSError, webbrowser.Error):
                opened = False
            if not opened:
                self.status.set('Tarayıcı açılamadı. Adres ' + self.ready_url)

    def drain(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except Empty:
                return
            if kind == 'lan':
                if self.profile == 'prod':
                    self._capture()
                if not self.forms['prod']['host']:
                    self.forms['prod']['host'] = value
                    if self.profile == 'prod' and 'host' not in self.locked:
                        self.variables['host'].set(value)
            elif kind == 'python':
                self.interpreters = value
                if self.profile:
                    self._show_python()
            elif kind == 'admin':
                self._prompt_admin(value)
            elif kind == 'ready' and not self.closing:
                url = _ready_url(value)
                first = url and url != self.ready_url
                self.ready_url = url
                self.status.set('Sunucu hazır. ' + url)
                self._update_buttons()
                if first:
                    self._browser()
            elif kind == 'tls' and isinstance(value, dict):
                for key in ('tls_cert_file', 'tls_key_file'):
                    if key in value and key not in self.locked:
                        self.variables[key].set(str(value[key]))
                self.save()
            elif kind == 'done':
                self.task = None
                self.stopping = False
                self.ready_url = ''
                self._update_buttons()
                self.status.set((self.last_error or safe_text(value) or 'İşlem tamamlandı.')[:180])
                if self.closing:
                    self.root.destroy()
                    return
            elif kind in ('status', 'error'):
                message = safe_text(value, limit=len(value)) if isinstance(value, str) else ''
                self.log.configure(state='normal')
                self.log.insert('end', message + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
                self.status.set(message[:180])
                if kind == 'error':
                    self.last_error = message
                    self.error_details.grid()

    def _poll(self):
        self.drain()
        if not self.closing or self.task:
            self.root.after(75, self._poll)

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.save()
        if self.task:
            self.stop()
        else:
            self.root.destroy()
