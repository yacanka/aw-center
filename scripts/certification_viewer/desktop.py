"""Windows file selection, remembered source and the lifetime of the browser viewer."""

from hashlib import sha256
import os
from pathlib import Path
from queue import Empty, Queue
from tempfile import NamedTemporaryFile, TemporaryDirectory
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from compliance.executable_config import validate_database_path
from compliance.offline_reader import DashboardReader

from .server import ViewerServer
from .source import DatabaseSource, SourceError, is_network_path


def preference_path(embedded, local_app_data):
    key = sha256(embedded.casefold().encode('utf-8')).hexdigest()
    return local_app_data / 'AWCenter' / 'CertificationDashboard' / 'sources' / (key + '.txt')


def remembered_source(preference):
    try:
        with preference.open(encoding='utf-8') as stream:
            return validate_database_path(stream.read(4097))
    except (OSError, ValueError):
        return None


def remember_source(preference, value):
    preference.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=preference.parent, delete=False, mode='w', encoding='utf-8') as temp:
        temporary = Path(temp.name)
        temp.write(value)
    try:
        os.replace(temporary, preference)
    finally:
        temporary.unlink(missing_ok=True)


def browser_handoff(server, directory):
    ticket = server.new_ticket()
    page = directory / 'open.html'
    # A short-lived POST keeps the ticket out of browser history, URLs and server logs.
    page.write_text(
        '<!doctype html><html lang="tr"><meta charset="utf-8"><title>Certification Dashboard</title>'
        f'<form method="post" action="{server.origin}/open"><input type="hidden" name="ticket" value="{ticket}">'
        '<button>Dashboard’u aç</button></form><script>document.forms[0].submit()</script></html>',
        encoding='utf-8',
    )
    return webbrowser.open(page.as_uri(), new=2)


class ViewerWindow:
    def __init__(self, root, assets, directory, embedded, trusted_network):
        self.root = root
        self.directory = directory
        self.assets = assets
        self.pending = None
        self.server = None
        self.worker = None
        self.closing = Event()
        self.events = Queue()
        self.preference = preference_path(embedded, Path(os.environ['LOCALAPPDATA']))
        self.remembered = remembered_source(self.preference)
        self.embedded = embedded
        self.trusted_network = trusted_network
        self.path = tk.StringVar(value=self.remembered or embedded)
        self.status = tk.StringVar()
        self.busy = False

        root.title('Certification Dashboard')
        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky='nsew')
        root.columnconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text='Veritabanı yolu').grid(sticky='w')
        entry = ttk.Entry(frame, textvariable=self.path, width=58)
        entry.grid(row=1, column=0, sticky='ew', pady=6)
        self.browse = ttk.Button(frame, text='Gözat…', command=self.choose)
        self.browse.grid(row=1, column=1, padx=(6, 0))
        self.submit = ttk.Button(frame, text='Dashboard’u aç', command=self.open)
        self.submit.grid(row=2, column=0, columnspan=2, sticky='w', pady=6)
        ttk.Label(frame, textvariable=self.status, wraplength=460).grid(row=3, columnspan=2, sticky='w')
        root.bind('<Return>', lambda _: self.open())
        root.protocol('WM_DELETE_WINDOW', self.close)
        entry.focus_set()
        root.after(50, self.open)
        root.after(100, self.poll)

    def choose(self):
        selected = filedialog.askopenfilename(
            parent=self.root, title='AW Center veritabanını seçin',
            filetypes=[('SQLite', '*.sqlite3 *.sqlite *.db'), ('Tüm dosyalar', '*.*')],
        )
        if selected:
            self.path.set(selected)

    def open(self):
        if self.busy or self.closing.is_set():
            return
        try:
            path = validate_database_path(self.path.get())
        except ValueError:
            self.status.set('Tam bir Windows dosya yolu girin veya Gözat ile bir SQLite dosyası seçin.')
            return
        if (is_network_path(Path(path)) and path != self.remembered
                and not (self.trusted_network and path == self.embedded)):
            if not messagebox.askyesno('Ağ yedeğini aç', f'Windows hesabınızla bu konuma bağlanılsın mı?\n\n{path}',
                                       parent=self.root):
                self.status.set('Başka bir veritabanı yolu girebilirsiniz.')
                return
        self.busy = True
        self.submit.state(['disabled'])
        self.browse.state(['disabled'])
        self.status.set('Veritabanı okunuyor…')
        self.pending = DatabaseSource(self.directory, DashboardReader)
        self.worker = Thread(target=self.load, args=(path, self.pending), daemon=True)
        self.worker.start()

    def load(self, path, source):
        try:
            source.select(Path(path))
            server = ViewerServer(source, self.assets)
        except (SourceError, OSError) as exc:
            source.close()
            message = str(exc) if isinstance(exc, SourceError) else 'Yerel görüntüleyici başlatılamadı.'
            self.events.put((path, message))
            return
        # An old tab must never silently read a different database using its old credentials.
        if self.server:
            self.stop_server(self.server)
        self.server = server
        Thread(target=server.serve_forever, daemon=True).start()
        self.events.put((path, ''))

    @staticmethod
    def stop_server(server):
        server.source.request_stop()
        server.shutdown()
        server.server_close()
        server.source.close()

    def poll(self):
        if self.closing.is_set():
            return
        try:
            path, error = self.events.get_nowait()
        except Empty:
            pass
        else:
            self.busy = False
            self.submit.state(['!disabled'])
            self.browse.state(['!disabled'])
            if error:
                self.status.set(error + ' Veritabanı yolunu girin veya Gözat ile seçin.')
            else:
                self.remembered = path
                try:
                    remember_source(self.preference, path)
                    saved = ''
                except OSError:
                    saved = ' Yol tercihi kaydedilemedi.'
                if browser_handoff(self.server, self.directory):
                    self.status.set('Dashboard tarayıcıda açık. Bu pencereyi kapattığınızda görüntüleyici kapanır.' + saved)
                else:
                    self.status.set('Tarayıcı açılamadı. Varsayılan tarayıcınızı kontrol edip tekrar deneyin.')
        self.root.after(100, self.poll)

    def close(self):
        if self.closing.is_set():
            return
        self.closing.set()
        self.submit.state(['disabled'])
        self.browse.state(['disabled'])
        self.status.set('Okuma tamamlanıyor ve geçici dosyalar temizleniyor…')
        if self.pending:
            self.pending.request_stop()
        if self.server:
            self.server.source.request_stop()
        shutting_down = Thread(target=self.shutdown)
        shutting_down.start()
        self.finish_close(shutting_down)

    def shutdown(self):
        if self.worker:
            self.worker.join()
        if self.server:
            self.stop_server(self.server)

    def finish_close(self, thread):
        if thread.is_alive():
            self.root.after(100, self.finish_close, thread)
        else:
            self.root.destroy()


def run_desktop(assets, embedded, trusted_network):
    root = tk.Tk()
    with TemporaryDirectory(prefix='AW-Certification-') as directory:
        ViewerWindow(root, assets, Path(directory), embedded, trusted_network)
        root.mainloop()
