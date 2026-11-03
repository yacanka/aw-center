"""Native Turkish desktop view; all installation work belongs to the controller."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
from threading import Thread
from typing import Callable
import webbrowser

from .view_model import DEFAULT_VALUES, FormError, ManagerTaskStates, normalize_values, safe_text, validate_admin


_ACTION_LABELS = {"provision": "Kur ve başlat", "start": "Başlat", "doctor": "Durumu denetle",
                  "test-sources": "Kaynakları dene", "bundle": "Çevrimdışı paket hazırla"}
_TASK_STATUSES = {"running": "Çalışıyor", "ready": "Hazır / çalışıyor", "stopping": "Durduruluyor",
                  "finishing": "Tamamlanıyor", "done": "Tamamlandı", "failed": "Başarısız",
                  "cancelled": "Durduruldu"}


class _ScrollPanel(ttk.Frame):
    """Keep form fields reachable with system text scaling and smaller displays."""

    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        background = ttk.Style(self).lookup("TFrame", "background")
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=background)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.body = ttk.Frame(self.canvas, padding=12)
        self._window = self.canvas.create_window(0, 0, anchor="nw", window=self.body)
        self.body.bind("<Configure>", self._content_changed)
        self.canvas.bind("<Configure>", self._resized)
        top = self.winfo_toplevel()
        top.bind("<MouseWheel>", self._wheel, add=True)
        top.bind("<Button-4>", self._wheel, add=True)
        top.bind("<Button-5>", self._wheel, add=True)
        top.bind("<FocusIn>", self._focus_changed, add=True)

    def _content_changed(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resized(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _contains(self, widget):
        return str(widget).startswith(str(self) + ".")

    def _wheel(self, event):
        if not self._contains(event.widget):
            return None
        direction = -1 if getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(direction * 3, "units")
        return "break"

    def _focus_changed(self, event):
        if not self._contains(event.widget):
            return
        top = event.widget.winfo_rooty() - self.body.winfo_rooty()
        bottom = top + event.widget.winfo_height()
        visible_top = self.canvas.canvasy(0)
        visible_bottom = visible_top + self.canvas.winfo_height()
        height = max(self.body.winfo_height(), 1)
        if top < visible_top:
            self.canvas.yview_moveto(max(top - 8, 0) / height)
        elif bottom > visible_bottom:
            self.canvas.yview_moveto((bottom + 8 - self.canvas.winfo_height()) / height)


class ManagerWindow:
    """Render safe structured events on the Tk thread without launching processes.

    The controller owns worker lifetime, cancellation, and close confirmation.
    Call ``handle_event`` and ``set_busy`` only from the Tk event loop.
    """

    def __init__(self, root, on_action: Callable, on_stop: Callable,
                 on_close: Callable, source_root=None):
        self.root = root
        self.on_action = on_action
        self.on_stop = on_stop
        self.task_states = ManagerTaskStates()
        self.on_open: Callable | None = None
        self._admin_dialogs: dict[str, dict] = {}
        self._progress_running = False
        self.variables = {key: (tk.BooleanVar(root, value=value) if isinstance(value, bool)
                                else tk.StringVar(root, value=value))
                          for key, value in DEFAULT_VALUES.items()}
        self.variables["source_root"].set(str(source_root or Path(__file__).resolve().parents[2]))
        self._controls: list[ttk.Widget] = []
        self._fields: dict[str, ttk.Entry] = {}
        self._field_titles: dict[str, str] = {}
        self._pickers: dict[str, ttk.Button] = {}
        self._field_tabs: dict[str, ttk.Frame] = {}
        self._wrapping: list[ttk.Label] = []
        self.status_var = tk.StringVar(root, value=self.state.status)
        self.error_var = tk.StringVar(root)
        self.source_help_var = tk.StringVar(root)
        self.profile_help_var = tk.StringVar(root)
        root.title("AW Center — Kurulum ve Çalıştırma")
        root.minsize(700, 560)
        root.geometry(f"{min(1000, root.winfo_screenwidth() - 60)}x{min(820, root.winfo_screenheight() - 100)}")
        root.protocol("WM_DELETE_WINDOW", on_close)
        self._build()
        self.variables["profile"].trace_add("write", lambda *_: self._update_controls())
        self.variables["source_mode"].trace_add("write", lambda *_: self._update_controls())
        root.bind("<Configure>", self._wrap_changed, add=True)
        root.bind("<Control-r>", lambda _event: self._retry())
        for number, tab in enumerate((self.run_tab, self.source_tab, self.report_tab), start=1):
            root.bind(f"<Control-Key-{number}>", lambda _event, selected=tab: self.tabs.select(selected))
        self._update_controls()

    @property
    def state(self):
        return self.task_states.current

    def _label(self, parent, text=None, **kwargs):
        label = ttk.Label(parent, text=text, wraplength=780, **kwargs)
        self._wrapping.append(label)
        return label

    def _build(self):
        shell = ttk.Frame(self.root, padding=12)
        shell.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(3, weight=1)
        heading_font = font.nametofont("TkDefaultFont").copy()
        heading_font.configure(size=heading_font.cget("size") + 4, weight="bold")
        self._heading_font = heading_font
        ttk.Label(shell, text="AW Center", font=heading_font).grid(row=0, column=0, sticky="w")
        self._label(shell, "Kurulum, çalışma ve kaynak denetimi. Dev ve prod profilleri ayrı tutulur.").grid(row=1, column=0, sticky="ew", pady=(4, 10))
        self._build_tasks(shell)
        self.tabs = ttk.Notebook(shell)
        self.tabs.grid(row=3, column=0, sticky="nsew")
        self.run_tab = _ScrollPanel(self.tabs)
        self.source_tab = _ScrollPanel(self.tabs)
        self.report_tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.run_tab, text="Çalışma (Ctrl+1)")
        self.tabs.add(self.source_tab, text="Kaynaklar (Ctrl+2)")
        self.tabs.add(self.report_tab, text="Durum ve rapor (Ctrl+3)")
        self._build_run(self.run_tab.body)
        self._build_sources(self.source_tab.body)
        self._build_report(self.report_tab)
        self._build_actions(shell)
        self.progress = ttk.Progressbar(shell, mode="indeterminate", takefocus=False)
        self.progress.grid(row=5, column=0, sticky="ew", pady=(8, 4))
        self._label(shell, textvariable=self.status_var).grid(row=6, column=0, sticky="ew")
        self._build_error(shell)

    def _build_tasks(self, parent):
        tasks = ttk.LabelFrame(parent, text="İşlemler — durum ve rapor için bir işlem seçin", padding=8)
        tasks.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        tasks.columnconfigure(0, weight=1)
        self.task_tree = ttk.Treeview(tasks, columns=("id", "action", "profile", "status"),
                                      show="headings", height=3, selectmode="browse")
        for key, label, width in (("id", "İşlem no", 80), ("action", "İşlem", 260), ("profile", "Profil", 70), ("status", "Durum", 180)):
            self.task_tree.heading(key, text=label)
            self.task_tree.column(key, width=width, minwidth=60)
        self.task_tree.grid(row=0, column=0, sticky="ew")
        scrollbar = ttk.Scrollbar(tasks, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.task_tree.bind("<<TreeviewSelect>>", self._select_task)
        ttk.Button(tasks, text="Genel bildirimler", command=self._show_general).grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _entry(self, parent, row, key, label, *, tab, picker=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        entry = ttk.Entry(parent, textvariable=self.variables[key], width=32)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        self._fields[key] = entry
        self._field_titles[key] = label
        self._field_tabs[key] = tab
        self._controls.append(entry)
        if picker:
            button = ttk.Button(parent, text="Seç…", command=lambda: self._pick(key, picker))
            button.grid(row=row, column=2, sticky="ew", padx=(8, 0), pady=5)
            self._pickers[key] = button
            self._controls.append(button)
        parent.columnconfigure(1, weight=1)
        return entry

    def _build_run(self, parent):
        parent.columnconfigure(0, weight=1)
        profile = ttk.LabelFrame(parent, text="Çalışma profili", padding=12)
        profile.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        for column, (value, label) in enumerate((("dev", "Geliştirme (dev)"), ("prod", "Üretim (prod)"))):
            button = ttk.Radiobutton(profile, text=label, value=value, variable=self.variables["profile"])
            button.grid(row=0, column=column, sticky="w", padx=(0, 24))
            self._controls.append(button)
        self._label(profile, textvariable=self.profile_help_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        paths = ttk.LabelFrame(parent, text="Kaynak ve profil seçenekleri", padding=12)
        paths.grid(row=1, column=0, sticky="ew")
        self._entry(paths, 0, "source_root", "Proje kaynak dizini", tab=self.run_tab, picker="directory")
        self._label(paths, "Aşağıdaki alanlar boşsa mevcut profil korunur; yeni dev profili varsayılanları 127.0.0.1, 8000 ve 5173'tür.").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        self._entry(paths, 2, "host", "Host / statik IPv4", tab=self.run_tab)
        self._entry(paths, 3, "backend_port", "Backend / HTTPS portu", tab=self.run_tab)
        self._entry(paths, 4, "frontend_port", "Frontend portu (dev)", tab=self.run_tab)
        self._entry(paths, 5, "tls_cert_file", "TLS sertifikası (prod)", tab=self.run_tab, picker="certificate")
        self._entry(paths, 6, "tls_key_file", "TLS özel anahtarı (prod)", tab=self.run_tab, picker="key")
        self._label(paths, "Yeni prod profili için sabit IPv4 ile kaynak dizini dışındaki TLS dosyaları gerekir. Prod kaynakları yönetilen release dizinine alınır.").grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        migrate = ttk.Checkbutton(paths, text="Mevcut veritabanının migration işlemlerini uygula", variable=self.variables["migrate"])
        migrate.grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._controls.append(migrate)

    def _build_sources(self, parent):
        parent.columnconfigure(0, weight=1)
        modes = ttk.LabelFrame(parent, text="Paket kaynakları", padding=12)
        modes.grid(row=0, column=0, sticky="ew")
        for column, (value, label) in enumerate((("online", "İnternet (Online)"), ("corporate", "Kurumsal (Corporate)"), ("offline", "Çevrimdışı (Offline)"))):
            button = ttk.Radiobutton(modes, text=label, value=value, variable=self.variables["source_mode"])
            button.grid(row=0, column=column, sticky="w", padx=(0, 16))
            self._controls.append(button)
        self._label(modes, textvariable=self.source_help_var).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        fields = ttk.Frame(parent)
        fields.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for row, (key, label, picker) in enumerate((
            ("repository", "Arşiv deposu / yerel dizin", "directory"),
            ("offline_dir", "Çevrimdışı bağımlılık dizini", "directory"),
            ("python_index_url", "Python paket indeksi (pip)", None),
            ("npm_registry_url", "JavaScript paket deposu (npm)", None),
            ("ca_file", "Kurumsal CA dosyası (PEM)", "certificate"),
            ("assets", "Onaylı asset dizini (isteğe bağlı)", "directory"),
            ("feature_catalog", "Native araç kataloğu (isteğe bağlı)", "catalog"),
            ("output", "Çevrimdışı paket çıktı dizini", "directory"),
        )):
            self._entry(fields, row, key, label, tab=self.source_tab, picker=picker)
        self._label(parent, "Python/Node/Git çalışma zamanı arşivleri yönetici paketine dahildir. pip ve npm alanları uygulama bağımlılıklarını belirler; arşiv deposu alanı bunlardan ayrıdır. URL'lere parola veya token yazmayın. TLS ve hash doğrulaması her modda korunur.").grid(row=2, column=0, sticky="ew", pady=(12, 0))

    def _build_report(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        self._label(parent, "Seçili işlemin kontrolleri ve güvenli durum raporu. Ham alt süreç çıktısı ve yönetici parolası rapora alınmaz.").grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.report_text = tk.Text(parent, wrap="word", width=60, height=12, state="disabled", font="TkDefaultFont", takefocus=True)
        scrollbar = ttk.Scrollbar(parent, command=self.report_text.yview)
        self.report_text.configure(yscrollcommand=scrollbar.set)
        self.report_text.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        # A native Text is needed for selectable reports; derive its appearance from ttk.
        style = ttk.Style(parent)
        for option, style_option in (("background", "fieldbackground"), ("foreground", "foreground")):
            color = style.lookup("TEntry", style_option)
            if color:
                self.report_text.configure(**{option: color})
        bar = ttk.Frame(parent)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(bar, text="Güvenli raporu kopyala", command=self._copy_report).grid(row=0, column=0, sticky="w")
        self.open_button = ttk.Button(bar, text="AW Center'ı tarayıcıda aç", command=self._open_ready, state="disabled")
        self.open_button.grid(row=0, column=1, sticky="w", padx=(12, 0))

    def _build_actions(self, parent):
        actions = ttk.Frame(parent)
        actions.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.action_buttons = {}
        for index, (action, label) in enumerate((
            ("provision", "Kur ve başlat"), ("start", "Başlat"),
            ("doctor", "Durumu denetle"), ("test-sources", "Kaynakları dene"),
            ("bundle", "Çevrimdışı paket hazırla"),
        )):
            button = ttk.Button(actions, text=label, command=lambda selected=action: self._dispatch(selected))
            button.grid(row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4)
            self.action_buttons[action] = button
        self.stop_button = ttk.Button(actions, text="Seçili işlemi durdur", command=self._stop_selected, state="disabled")
        self.stop_button.grid(row=1, column=2, sticky="ew", padx=4, pady=4)
        for column in range(3):
            actions.columnconfigure(column, weight=1)

    def _build_error(self, parent):
        self.error_frame = ttk.LabelFrame(parent, text="İşlem sonucu / çözüm", padding=10)
        self.error_frame.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        self.error_frame.columnconfigure(0, weight=1)
        self._label(self.error_frame, textvariable=self.error_var).grid(row=0, column=0, sticky="ew")
        bar = ttk.Frame(self.error_frame)
        bar.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.retry_button = ttk.Button(bar, text="Son işlemi yeniden dene (Ctrl+R)", command=self._retry)
        self.retry_button.grid(row=0, column=0, sticky="w")
        ttk.Button(bar, text="Kaynakları değiştir", command=self._show_sources).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(bar, text="Raporu kopyala", command=self._copy_report).grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.error_frame.grid_remove()

    def _pick(self, key, kind):
        options = {"parent": self.root, "title": self._field_titles[key]}
        if kind == "directory":
            value = filedialog.askdirectory(**options, mustexist=(key != "output"))
        else:
            patterns = {"certificate": [("PEM / sertifika", "*.pem *.crt *.cer"), ("Tüm dosyalar", "*")],
                        "key": [("PEM / özel anahtar", "*.pem *.key"), ("Tüm dosyalar", "*")],
                        "catalog": [("JSON kataloğu", "*.json"), ("Tüm dosyalar", "*")]}
            value = filedialog.askopenfilename(**options, filetypes=patterns[kind])
        if value:
            self.variables[key].set(value)

    def _dispatch(self, action, values=None):
        try:
            submitted = normalize_values(action, values if values is not None else {key: variable.get() for key, variable in self.variables.items()})
        except FormError as error:
            self._show_form_error(error)
            return
        self.task_states.general.record_action(action, submitted)
        self.task_states.general.busy = False
        self._refresh()
        try:
            self.on_action(action, submitted)
        except Exception:
            # Tk's default callback traceback could expose exception payloads.
            self.handle_event({"type": "error", "code": "manager_action_failed", "message": "İşlem başlatılamadı.", "remedy": "Güvenli raporu inceleyip işlemi yeniden deneyin."})
            self.handle_event({"type": "done", "ok": False})

    def _show_form_error(self, error):
        self.handle_event({"type": "error", "code": "invalid_form", "message": str(error), "remedy": "Belirtilen alanı düzeltip işlemi yeniden başlatın."})
        tab = self._field_tabs.get(error.field)
        if tab:
            self.tabs.select(tab)
        field = self._fields.get(error.field)
        if field:
            field.focus_set()

    def _retry(self):
        if self.state.last_action:
            self._dispatch(self.state.last_action)

    def _show_sources(self):
        self.tabs.select(self.source_tab)
        self._fields["offline_dir" if self.variables["source_mode"].get() == "offline" else "repository"].focus_set()

    def _copy_report(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.state.report())
        except tk.TclError:
            self.status_var.set("Panoya erişilemedi. Rapor sekmesindeki metni seçip kopyalayabilirsiniz.")
            return
        self.status_var.set("Güvenli durum raporu panoya kopyalandı.")

    def _open_ready(self):
        url = self.state.ready_url
        if not url:
            return
        if self.on_open:
            self.on_open(url, self.selected_task_id())
        else:
            Thread(target=self._open_browser, args=(url,), daemon=True).start()

    @staticmethod
    def _open_browser(url):
        try:
            webbrowser.open(url, new=2)
        except Exception:
            pass  # Browser helpers must never log a host exception or touch Tk.

    def _wrap_changed(self, event):
        if event.widget is self.root:
            for label in self._wrapping:
                label.configure(wraplength=max(300, event.width - 100))

    def _update_controls(self):
        for control in self._controls:
            control.configure(state="normal")
        profile = self.variables["profile"].get()
        mode = self.variables["source_mode"].get()
        disabled = {"frontend_port"} if profile == "prod" else {"tls_cert_file", "tls_key_file"}
        if mode == "offline":
            disabled.update({"repository", "python_index_url", "npm_registry_url"})
        for key in disabled:
            self._fields[key].configure(state="disabled")
            if key in self._pickers:
                self._pickers[key].configure(state="disabled")
        for button in self.action_buttons.values():
            button.configure(state="normal")
        selected = self.task_states.tasks.get(self.selected_task_id(), {})
        self.stop_button.configure(state="normal" if selected.get("status") in ManagerTaskStates.ACTIVE_STATUSES else "disabled")
        self.retry_button.configure(state="normal" if self.state.last_action else "disabled")
        self.open_button.configure(state="normal" if self.state.ready_url else "disabled")
        self.profile_help_var.set("Dev: yerel geliştirme sunucuları; host 127.0.0.1 ile sınırlıdır." if profile == "dev" else "Prod: HTTPS, sabit IPv4 ve ayrı özel veritabanı / artifact dizinleri.")
        self.source_help_var.set({
            "online": "İnternet kaynakları kullanılır. İsteğe bağlı kurumsal ve çevrimdışı yedek kaynaklar aşağıdan seçilebilir.",
            "corporate": "Açıkça belirttiğiniz kurumsal HTTPS depoları veya yerel paket dizinleri kullanılır. CA dosyasını gerekiyorsa seçin.",
            "offline": "Ağ kullanılmaz. Doğrulanmış uygulama bağımlılıklarını içeren çevrimdışı paket dizini zorunludur.",
        }.get(mode, "Kaynak modu seçin."))

    def set_busy(self, busy: bool):
        """Compatibility hook; input controls remain usable during operations."""
        self.state.busy = bool(busy)
        self._refresh()

    def _refresh(self):
        if self.state.busy != self._progress_running:
            self.progress.start(15) if self.state.busy else self.progress.stop()
            self._progress_running = self.state.busy
        self.status_var.set(self.state.status)
        if self.state.error_message:
            details = self.state.error_message[:300] + "\nÇözüm: " + self.state.error_remedy[:300]
            if len(self.state.error_message) > 300 or len(self.state.error_remedy) > 300:
                details += "\nAyrıntıların tamamı durum ve rapor sekmesindedir."
            if self.state.error_code:
                details += "\nKod: " + self.state.error_code
            self.error_var.set(details)
            self.error_frame.grid()
        else:
            self.error_var.set("")
            self.error_frame.grid_remove()
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", self.state.report())
        self.report_text.configure(state="disabled")
        self._update_controls()

    def handle_event(self, event: dict):
        self.task_states.handle_event(event)
        self._sync_task_selection()
        self._refresh()

    def selected_task_id(self) -> str | None:
        return self.task_states.selected_id

    def update_tasks(self, tasks: list[dict], selected_id: str | None = None):
        """Render controller-owned lifecycle rows without replacing task reports."""
        self.task_states.update_tasks(tasks, selected_id)
        existing = set(self.task_tree.get_children())
        for task_id, task in self.task_states.tasks.items():
            values = (safe_text(task_id, limit=8),
                      _ACTION_LABELS.get(task["action"], safe_text(task["action"], limit=80)),
                      safe_text(task["profile"], limit=30),
                      _TASK_STATUSES.get(task["status"], "Bilinmiyor"))
            if task_id in existing:
                self.task_tree.item(task_id, values=values)
            else:
                self.task_tree.insert("", "end", iid=task_id, values=values)
        for task_id in existing - self.task_states.tasks.keys():
            self.task_tree.delete(task_id)
        self._sync_task_selection()
        self._refresh()

    def _sync_task_selection(self):
        selected = self.selected_task_id()
        if selected is not None:
            self.task_tree.selection_set(selected)
            self.task_tree.see(selected)
        else:
            self.task_tree.selection_remove(self.task_tree.selection())

    def _select_task(self, _event=None):
        selected = self.task_tree.selection()
        self.task_states.select(selected[0] if selected else None)
        self._refresh()

    def _show_general(self):
        self.task_states.select(None)
        self._sync_task_selection()
        self._refresh()

    def _stop_selected(self):
        self.on_stop()

    def confirm_stop(self) -> bool:
        count = sum(task["status"] in ManagerTaskStates.ACTIVE_STATUSES for task in self.task_states.tasks.values())
        return messagebox.askyesno("Tüm çalışan işlemleri durdur", f"Pencere kapatıldığında tüm çalışan işlemler ({count}) ve onlara bağlı süreçler güvenli biçimde durdurulacak. Devam etmek istiyor musunuz?", parent=self.root, default="no")

    def request_admin(self, task_id: str, callback: Callable[[dict[str, str] | None], None]) -> None:
        """Collect credentials without blocking polling or other task interactions."""
        if task_id in self._admin_dialogs:
            self._admin_dialogs[task_id]["dialog"].lift()
            return
        dialog = tk.Toplevel(self.root)
        task = self.task_states.tasks.get(task_id, {})
        context = f"{task.get('profile', '')} / {_ACTION_LABELS.get(task.get('action'), 'İşlem')}"
        dialog.title("İlk yönetici hesabı — " + context)
        dialog.transient(self.root)
        dialog.resizable(True, False)
        dialog.columnconfigure(0, weight=1)
        body = ttk.Frame(dialog, padding=16)
        body.grid(sticky="ew")
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="İlk yönetici hesabını oluşturun. Kullanıcı adı bir harf ve beş rakamdır (örnek: U12345). Parola rapora veya profil dosyasına yazılmaz.", wraplength=500).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        variables = {key: tk.StringVar(dialog) for key in ("username", "password", "confirmation")}
        self._admin_dialogs[task_id] = {"dialog": dialog, "variables": variables, "callback": callback}
        fields = {}
        for row, (key, label) in enumerate((("username", "Kullanıcı adı"), ("password", "Parola"), ("confirmation", "Parola tekrarı")), start=1):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
            entry = ttk.Entry(body, textvariable=variables[key], width=36, show="*" if key != "username" else "")
            entry.grid(row=row, column=1, sticky="ew", pady=6)
            fields[key] = entry
        ttk.Label(body, text="8–128 karakter; yalnız rakam kullanmayın. Uygulamanın parola güvenliği denetimleri de uygulanır.", wraplength=500).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        error_var = tk.StringVar(dialog)
        ttk.Label(body, textvariable=error_var, wraplength=500).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        def submit():
            try:
                result = validate_admin(*(variables[key].get() for key in ("username", "password", "confirmation")))
            except FormError as error:
                error_var.set(str(error))
                fields[error.field].focus_set()
                return
            self._finish_admin(task_id, result)

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="İptal", command=lambda: self._finish_admin(task_id, None)).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Yönetici oluştur", command=submit).grid(row=0, column=1)
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._finish_admin(task_id, None))
        dialog.bind("<Escape>", lambda _event: self._finish_admin(task_id, None))
        dialog.bind("<Return>", lambda _event: submit())
        dialog.bind("<Destroy>", lambda event: self._finish_admin(task_id, None) if event.widget is dialog else None)
        fields["username"].focus_set()

    def dismiss_admin(self, task_id: str) -> None:
        """Wipe a task's prompt after cancellation without invoking its reply."""
        self._finish_admin(task_id, None, notify=False)

    def _finish_admin(self, task_id: str, value: dict[str, str] | None, *, notify=True):
        pending = self._admin_dialogs.pop(task_id, None)
        if pending is None:
            return
        for variable in pending["variables"].values():
            try:
                variable.set("")
            except tk.TclError:
                pass  # The root may already be closing during task cancellation.
        try:
            pending["dialog"].destroy()
        except tk.TclError:
            pass
        if notify:
            try:
                pending["callback"](value)
            except Exception:
                self.handle_event({"task_id": task_id, "type": "error", "code": "admin_reply_failed",
                                   "message": "Yönetici hesabı yanıtı gönderilemedi.",
                                   "remedy": "İşlemi durdurup yeniden deneyin."})
