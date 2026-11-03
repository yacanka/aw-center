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


class _Card(ttk.Frame):
    """Rounded presentation surface; children remain native accessible widgets."""

    def __init__(self, parent, *, padding=16):
        super().__init__(parent, padding=padding, style="Manager.TFrame")
        style = ttk.Style(self)
        self._fill = style.lookup("Manager.Panel.TFrame", "background")
        self._border = style.lookup("Manager.Card.TFrame", "bordercolor")
        self._backdrop = tk.Canvas(self, borderwidth=0, highlightthickness=0, takefocus=False,
                                  background=style.lookup("Manager.TFrame", "background"))
        self._backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lower(self._backdrop)
        self.bind("<Configure>", self._draw, add=True)

    def _draw(self, event):
        width, height, radius = event.width - 1, event.height - 1, 10
        self._backdrop.delete("surface")
        self._backdrop.create_polygon(
            radius, 1, width-radius, 1, width, 1, width, radius,
            width, height-radius, width, height, width-radius, height,
            radius, height, 1, height, 1, height-radius, 1, radius, 1, 1,
            smooth=True, splinesteps=24, fill=self._fill, outline=self._border, tags="surface")


class _ScrollPanel(ttk.Frame):
    """Keep form fields reachable with system text scaling and smaller displays."""

    def __init__(self, parent):
        super().__init__(parent, style="Manager.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        background = ttk.Style(self).lookup("Manager.TFrame", "background")
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=background)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.body = ttk.Frame(self.canvas, padding=18, style="Manager.TFrame")
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

    _advanced_fields = frozenset({"frontend_port", "tls_cert_file", "tls_key_file",
                                  "migrate", "install_python", "env_file"})

    def __init__(self, root, on_action: Callable, on_stop: Callable,
                 on_close: Callable, source_root=None):
        self.root = root
        self.on_action = on_action
        self.on_stop = on_stop
        self.task_states = ManagerTaskStates()
        self.on_open: Callable | None = None
        self._admin_dialogs: dict[str, dict] = {}
        self._progress_running = False
        self._compact_layout = None
        self._tasks_expanded = True
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
        self.advanced_var = tk.BooleanVar(root, value=False)
        self.summary_title_var = tk.StringVar(root)
        self.summary_context_var = tk.StringVar(root)
        self.task_count_var = tk.StringVar(root)
        root.title("AW Center Manager")
        root.minsize(700, 560)
        root.geometry(f"{min(1000, root.winfo_screenwidth() - 60)}x{min(820, root.winfo_screenheight() - 100)}")
        root.protocol("WM_DELETE_WINDOW", on_close)
        self._build()
        self.variables["profile"].trace_add("write", lambda *_: self._profile_changed())
        self.variables["source_mode"].trace_add("write", lambda *_: self._update_controls())
        root.bind("<Configure>", self._layout_changed, add=True)
        root.bind("<Control-r>", lambda _event: self._retry())
        for number, tab in enumerate((self.run_tab, self.source_tab, self.report_tab), start=1):
            root.bind(f"<Control-Key-{number}>", lambda _event, selected=tab: self.tabs.select(selected))
        self._update_controls()

    @property
    def state(self):
        return self.task_states.current

    def _label(self, parent, text=None, **kwargs):
        kwargs.setdefault("style", "Manager.Panel.TLabel")
        # Grid supplies the width. Wrapping must not change the label's requested
        # width and feed a resize loop back into the surrounding grid.
        kwargs.setdefault("width", 1)
        label = ttk.Label(parent, text=text, wraplength=780, **kwargs)
        label.bind("<Configure>", self._wrap_changed, add=True)
        self._wrapping.append(label)
        return label

    def _configure_styles(self):
        """Apply the approved mockup palette, following the native appearance."""
        style = ttk.Style(self.root)
        native_surface = style.lookup("TEntry", "fieldbackground") or self.root.cget("background")
        dark_surface = sum(self.root.winfo_rgb(native_surface)) < 3 * 32768
        background, surface, foreground, muted, border = (
            ("#17191c", "#212428", "#edf0f2", "#aab2ba", "#363b40") if dark_surface else
            ("#f5f6f7", "#ffffff", "#20262c", "#626c76", "#e3e7e9"))
        accent = "#63d8a7" if dark_surface else "#147d53"
        soft = "#1d382c" if dark_surface else "#eaf6f0"
        # Clam provides paintable ttk elements on Windows too; native Vista
        # elements otherwise ignore the mockup's surfaces and control colors.
        style.theme_use("clam")
        style.configure("TFrame", background=background)
        style.configure("TLabel", background=background, foreground=foreground)
        style.configure("TButton", background=surface, foreground=foreground, bordercolor=border,
                        lightcolor=surface, darkcolor=surface, padding=(12, 4))
        style.map("TButton", background=[("active", soft)], bordercolor=[("focus", accent)])
        style.configure("TEntry", fieldbackground=surface, foreground=foreground, bordercolor=border,
                        lightcolor=surface, darkcolor=surface, padding=(9, 7), insertcolor=foreground)
        style.map("TEntry", bordercolor=[("focus", accent)])
        self._heading_font = font.nametofont("TkDefaultFont").copy()
        self._heading_font.configure(size=self._heading_font.cget("size") + 6, weight="bold")
        self._section_font = font.nametofont("TkDefaultFont").copy()
        self._section_font.configure(weight="bold")
        for name, color in (("Manager.TFrame", background), ("Manager.Panel.TFrame", surface)):
            style.configure(name, background=color)
        style.configure("Manager.Card.TFrame", background=surface, bordercolor=border)
        style.configure("Manager.TLabel", background=background, foreground=foreground)
        style.configure("Manager.Title.TLabel", background=background, foreground=foreground, font=self._heading_font)
        style.configure("Manager.Panel.TLabel", background=surface, foreground=foreground)
        style.configure("Manager.Muted.TLabel", background=background, foreground=muted)
        style.configure("Manager.PanelMuted.TLabel", background=surface, foreground=muted)
        style.configure("Manager.Brand.TLabel", background=background, foreground=foreground, font=self._section_font)
        style.configure("Manager.Logo.TLabel", background=accent, foreground=background if dark_surface else surface,
                        padding=(8, 4), font=self._section_font)
        style.configure("Manager.Section.TLabel", background=surface, foreground=foreground, font=self._section_font)
        style.configure("Manager.TRadiobutton", background=surface, padding=(0, 5))
        style.map("Manager.TRadiobutton", background=[("active", surface)])
        style.configure("Manager.TCheckbutton", background=surface, padding=(0, 4))
        style.map("Manager.TCheckbutton", background=[("active", surface)])
        style.configure("Manager.TButton", padding=(12, 7))
        style.configure("Manager.Link.TButton", padding=(8, 5))
        style.configure("Manager.Treeview", rowheight=max(28, self._section_font.metrics("linespace") + 10))
        style.configure("Manager.Treeview.Heading", font=self._section_font)
        style.configure("Manager.Treeview", background=surface, fieldbackground=surface,
                        foreground=foreground, borderwidth=0)
        style.configure("Manager.Treeview.Heading", background=surface, foreground=muted,
                        relief="flat", padding=(10, 8))
        style.map("Manager.Treeview", background=[("selected", soft)], foreground=[("selected", foreground)])
        style.configure("Manager.TNotebook", background=background, borderwidth=0, tabmargins=0)
        self._tab_images = []
        for selected in (False, True):
            image = tk.PhotoImage(master=self.root, width=8, height=8)
            image.put(background, to=(0, 0, 8, 8))
            if selected:
                image.put(accent, to=(0, 6, 8, 8))
            self._tab_images.append(image)
        tab_element = f"Manager.tab.{id(self)}"
        style.element_create(tab_element, "image", self._tab_images[0],
                             ("selected", self._tab_images[1]), border=(0, 0, 0, 2), sticky="nsew")
        style.layout("Manager.TNotebook.Tab", [(tab_element, {"sticky": "nsew", "children": [
            ("Notebook.padding", {"sticky": "nsew", "children": [("Notebook.label", {"sticky": "nsew"})]})]})])
        style.configure("Manager.TNotebook.Tab", padding=(16, 9), foreground=muted, background=background)
        style.map("Manager.TNotebook.Tab", foreground=[("selected", accent)])
        # Native Windows button elements ignore background colors. Clam's border
        # gives this one ttk button a reliable accent without changing the theme.
        element = "Manager.Button.border"
        if element not in style.element_names():
            style.element_create(element, "from", "clam", "Button.border")
        style.layout("Manager.Primary.TButton", [(element, {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]})]})])
        style.configure("Manager.Primary.TButton", background=accent,
                        foreground=background if dark_surface else surface,
                        bordercolor=accent, lightcolor=accent, darkcolor=accent,
                        borderwidth=2, padding=(14, 8), font=self._section_font)
        style.map("Manager.Primary.TButton", background=[("disabled", background), ("active", accent)],
                  foreground=[("disabled", foreground)],
                  bordercolor=[("disabled", background), ("focus", foreground)],
                  lightcolor=[("focus", foreground)], darkcolor=[("focus", foreground)])
        style.layout("Manager.TRadiobutton", style.layout("Manager.Primary.TButton"))
        style.configure("Manager.TRadiobutton", background=surface, foreground=muted,
                        bordercolor=border, lightcolor=surface, darkcolor=surface, padding=(12, 6))
        style.map("Manager.TRadiobutton", background=[("selected", soft), ("active", soft)],
                  foreground=[("selected", accent)], bordercolor=[("focus", accent), ("selected", accent)])

    def _build(self):
        self._configure_styles()
        shell = ttk.Frame(self.root, padding=(20, 16, 20, 12), style="Manager.TFrame")
        shell.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        header = ttk.Frame(shell, style="Manager.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(0, weight=0)
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="AW", style="Manager.Logo.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(header, text="Center Manager", style="Manager.Brand.TLabel").grid(row=0, column=1, sticky="w")
        self.tabs = ttk.Notebook(shell, style="Manager.TNotebook")
        self.tabs.grid(row=1, column=0, sticky="nsew")
        self.run_tab = _ScrollPanel(self.tabs)
        self.source_tab = _ScrollPanel(self.tabs)
        self.report_tab = ttk.Frame(self.tabs, padding=14, style="Manager.Panel.TFrame")
        self.tabs.add(self.run_tab, text="Çalışma")
        self.tabs.add(self.source_tab, text="Paket kaynakları")
        self.tabs.add(self.report_tab, text="Durum ve rapor")
        self._build_run(self.run_tab.body)
        self._build_sources(self.source_tab.body)
        self._build_report(self.report_tab)
        self._build_actions()
        self._build_tasks(shell)
        self._build_error(shell)
        footer = ttk.Frame(shell, style="Manager.TFrame")
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, mode="indeterminate", takefocus=False)
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.progress.grid_remove()
        self._label(footer, textvariable=self.status_var, style="Manager.TLabel").grid(row=1, column=0, sticky="ew")

    def _build_tasks(self, parent):
        tasks = _Card(parent, padding=14)
        tasks.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        tasks.columnconfigure(0, weight=1)
        bar = ttk.Frame(tasks, style="Manager.Panel.TFrame")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, text="İşlemler", style="Manager.Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(bar, textvariable=self.task_count_var, style="Manager.Panel.TLabel").grid(row=0, column=1, padx=12)
        self.task_toggle_button = ttk.Button(bar, text="Listeyi gizle", command=self._toggle_task_details)
        self.task_toggle_button.grid(row=0, column=2, padx=(0, 8))
        self.stop_button = ttk.Button(bar, text="Seçili işlemi durdur", command=self._stop_selected, state="disabled")
        self.stop_button.grid(row=0, column=3, sticky="e")
        self.task_tree = ttk.Treeview(tasks, columns=("id", "action", "profile", "status"),
                                      show="headings", height=3, selectmode="browse", style="Manager.Treeview")
        for key, label, width in (("id", "İşlem no", 80), ("action", "İşlem", 260), ("profile", "Profil", 70), ("status", "Durum", 180)):
            self.task_tree.heading(key, text=label)
            self.task_tree.column(key, width=width, minwidth=60)
        self.task_tree.grid(row=1, column=0, sticky="ew")
        self.task_scrollbar = ttk.Scrollbar(tasks, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=self.task_scrollbar.set)
        self.task_scrollbar.grid(row=1, column=1, sticky="ns")
        self.task_tree.bind("<<TreeviewSelect>>", self._select_task)
        self.task_tree.bind("<Double-1>", lambda _event: self.tabs.select(self.report_tab))
        self.task_tree.bind("<Return>", lambda _event: self.tabs.select(self.report_tab))
        links = self.task_links = ttk.Frame(tasks, style="Manager.Panel.TFrame")
        links.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        links.columnconfigure(0, weight=1)
        ttk.Button(links, text="Genel bildirimler", command=self._show_general).grid(row=0, column=0, sticky="w")
        ttk.Button(links, text="Raporu incele", command=lambda: self.tabs.select(self.report_tab)).grid(row=0, column=1, sticky="e")

    def _set_task_details(self, expanded: bool):
        self._tasks_expanded = expanded
        for widget in (self.task_tree, self.task_scrollbar, self.task_links):
            widget.grid() if expanded else widget.grid_remove()
        self.task_toggle_button.configure(text="Listeyi gizle" if expanded else "Listeyi göster")

    def _toggle_task_details(self):
        self._set_task_details(not self._tasks_expanded)

    def _entry(self, parent, row, key, label, *, tab, picker=None, stacked=False):
        ttk.Label(parent, text=label, style="Manager.Panel.TLabel").grid(
            row=row-1 if stacked else row, column=0, columnspan=3 if stacked else 1,
            sticky="w", padx=(0, 12), pady=(0, 6) if stacked else 7)
        entry = ttk.Entry(parent, textvariable=self.variables[key], width=32)
        entry.grid(row=row, column=0 if stacked else 1, columnspan=2 if stacked else 1, sticky="ew", pady=7)
        self._fields[key] = entry
        self._field_titles[key] = label
        self._field_tabs[key] = tab
        self._controls.append(entry)
        if picker:
            button = ttk.Button(parent, text="Seç…", command=lambda: self._pick(key, picker))
            button.grid(row=row, column=2, sticky="ew", padx=(8, 0), pady=7)
            self._pickers[key] = button
            self._controls.append(button)
        parent.columnconfigure(1, weight=1)
        return entry

    def _build_run(self, parent):
        parent.columnconfigure(0, weight=1)
        intro = ttk.Frame(parent, style="Manager.TFrame")
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        intro.columnconfigure(0, weight=1)
        self._label(intro, "ÇALIŞMA ALANI", style="Manager.Muted.TLabel").grid(row=0, column=0, sticky="ew")
        self._label(intro, "Çalışma ortamınızı yönetin.", style="Manager.Title.TLabel").grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self._label(intro, "Ortamı yönetin, işlemleri tek yerden izleyin.", style="Manager.Muted.TLabel").grid(row=2, column=0, sticky="ew", pady=(6, 0))
        summary = _Card(parent)
        summary.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        summary.columnconfigure(0, weight=1)
        self._label(summary, textvariable=self.summary_title_var, style="Manager.Section.TLabel").grid(row=0, column=0, sticky="ew")
        self._label(summary, textvariable=self.summary_context_var).grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.banner_actions = ttk.Frame(summary, style="Manager.Panel.TFrame")
        self.banner_actions.grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))
        self.open_button = ttk.Button(self.banner_actions, text="Tarayıcıda aç", command=self._open_ready,
                                      style="Manager.Primary.TButton", state="disabled")
        self.open_button.grid(row=0, column=0)
        self.banner_stop_button = ttk.Button(self.banner_actions, text="Durdur", command=self._stop_selected,
                                             style="Manager.TButton", state="disabled")
        self.banner_stop_button.grid(row=0, column=1, padx=(8, 0))
        paths = self.run_settings = _Card(parent, padding=20)
        paths.grid(row=2, column=0, sticky="ew")
        ttk.Label(paths, text="Çalışma ayarları", style="Manager.Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        profile = ttk.Frame(paths, style="Manager.Panel.TFrame")
        profile.grid(row=0, column=1, columnspan=2, sticky="e")
        for column, (value, label) in enumerate((("dev", "Geliştirme (dev)"), ("prod", "Üretim (prod)"))):
            button = ttk.Radiobutton(profile, text=label, value=value, variable=self.variables["profile"], style="Manager.TRadiobutton")
            button.grid(row=0, column=column, sticky="w", padx=(12, 0))
            self._controls.append(button)
        self._label(paths, textvariable=self.profile_help_var).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        source = ttk.Frame(paths, style="Manager.Panel.TFrame")
        source.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        source.columnconfigure(1, weight=1)
        self._entry(source, 1, "source_root", "Proje kaynak dizini", tab=self.run_tab, picker="directory", stacked=True)
        connection = ttk.Frame(paths, style="Manager.Panel.TFrame")
        connection.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for column, (key, title) in enumerate((("host", "Host / statik IPv4"), ("backend_port", "Backend / HTTPS portu"))):
            connection.columnconfigure(column, weight=1, uniform="connection")
            field = ttk.Frame(connection, style="Manager.Panel.TFrame")
            field.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 10, 0))
            field.columnconfigure(0, weight=1)
            ttk.Label(field, text=title, style="Manager.Panel.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
            entry = ttk.Entry(field, textvariable=self.variables[key], width=12)
            entry.grid(row=1, column=0, sticky="ew")
            self._fields[key], self._field_titles[key], self._field_tabs[key] = entry, title, self.run_tab
            self._controls.append(entry)
        self._label(paths, "Boş alanlar mevcut profili korur. Yeni dev profili: 127.0.0.1, backend 8000, frontend 5173.").grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 12))
        ttk.Separator(paths).grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.advanced_button = ttk.Button(paths, text="Gelişmiş ayarları göster", command=self._toggle_advanced,
                                          style="Manager.Link.TButton")
        self.advanced_button.grid(row=7, column=0, columnspan=3, sticky="w")
        self.advanced_frame = ttk.Frame(paths, style="Manager.Panel.TFrame")
        self.advanced_frame.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self._build_advanced(self.advanced_frame)
        self.advanced_frame.grid_remove()

    def _build_advanced(self, parent):
        self._entry(parent, 0, "frontend_port", "Frontend portu (dev)", tab=self.run_tab)
        self._entry(parent, 1, "tls_cert_file", "TLS sertifikası (prod)", tab=self.run_tab, picker="certificate")
        self._entry(parent, 2, "tls_key_file", "TLS özel anahtarı (prod)", tab=self.run_tab, picker="key")
        self._label(parent, "Yeni prod profili için makineye atanmış sabit IPv4 ve kaynak dizini dışındaki TLS dosyaları gerekir.").grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        migrate = ttk.Checkbutton(parent, text="Mevcut veritabanının migration işlemlerini uygula",
                                  variable=self.variables["migrate"], style="Manager.TCheckbutton")
        migrate.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._controls.append(migrate)
        python = ttk.Checkbutton(parent, text="Python çalışma zamanını kur (isteğe bağlı)",
                                 variable=self.variables['install_python'], style="Manager.TCheckbutton")
        python.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._controls.append(python)
        self._label(parent, "Seçilmezse sistemdeki CPython 3.11 x64 kullanılır. Uygun Python yoksa otomatik kurulmaz. pip paketleri ayrı sanal ortama kurulur.").grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        self._entry(parent, 7, 'env_file', '.env dosyası (isteğe bağlı)', tab=self.run_tab, picker='environment')
        self._label(parent, 'Kur ve başlat seçilen dosyayı özel profile aktarır; kaynak dosya değiştirilmez. Boşsa mevcut profil veya otomatik yapılandırma kullanılır. Değişmiş dosyayı önce Kur ve başlat ile uygulayın.').grid(row=8, column=0, columnspan=3, sticky='ew', pady=(4, 0))

    def _set_advanced(self, expanded: bool):
        self.advanced_var.set(expanded)
        self.advanced_frame.grid() if expanded else self.advanced_frame.grid_remove()
        self.advanced_button.configure(text="Gelişmiş ayarları gizle" if expanded else "Gelişmiş ayarları göster")

    def _toggle_advanced(self):
        self._set_advanced(not self.advanced_var.get())

    def _profile_changed(self):
        if self.variables["profile"].get() == "prod":
            self._set_advanced(True)
        self._update_controls()

    def _build_sources(self, parent):
        parent.columnconfigure(0, weight=1)
        modes = _Card(parent)
        modes.grid(row=0, column=0, sticky="ew")
        ttk.Label(modes, text="Paket kaynakları", style="Manager.Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        for column, (value, label) in enumerate((("online", "İnternet (Online)"), ("corporate", "Kurumsal (Corporate)"), ("offline", "Çevrimdışı (Offline)"))):
            button = ttk.Radiobutton(modes, text=label, value=value, variable=self.variables["source_mode"], style="Manager.TRadiobutton")
            button.grid(row=1, column=column, sticky="w", padx=(0, 16))
            self._controls.append(button)
        self._label(modes, textvariable=self.source_help_var).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        fields = _Card(parent)
        fields.grid(row=1, column=0, sticky="ew", pady=(16, 0))
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
        self._label(parent, "İsteğe bağlı yönetilen Python, Node ve npm arşivleri yönetici paketine dahildir. pip ve npm alanları uygulama bağımlılıklarını belirler; arşiv deposu alanı bunlardan ayrıdır. URL'lere parola veya token yazmayın. TLS ve hash doğrulaması her modda korunur.", style="Manager.TLabel").grid(row=2, column=0, sticky="ew", pady=(12, 0))

    def _build_report(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        self._label(parent, "Seçili işlemin güvenli durum raporu.").grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.report_text = tk.Text(parent, wrap="word", width=60, height=12, state="disabled", font="TkDefaultFont", takefocus=True, borderwidth=0, padx=12, pady=12)
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
        bar = ttk.Frame(parent, style="Manager.Panel.TFrame")
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(bar, text="Güvenli raporu kopyala", command=self._copy_report).grid(row=0, column=0, sticky="w")
        self.report_open_button = ttk.Button(bar, text="Tarayıcıda aç", command=self._open_ready, state="disabled")
        self.report_open_button.grid(row=0, column=1, sticky="w", padx=(12, 0))

    def _build_actions(self):
        """Place each operation with its inputs; stopping remains task-scoped."""
        self.action_buttons = {"start": ttk.Button(self.banner_actions, text="Başlat", style="Manager.Primary.TButton",
                                                   command=lambda: self._dispatch("start"))}
        self.action_buttons["start"].grid(row=0, column=0)
        for parent, row, names in ((self.run_settings, 9, ("doctor", "provision")),
                                   (self.source_tab.body, 3, ("test-sources", "bundle"))):
            actions = ttk.Frame(parent, style="Manager.Panel.TFrame" if parent is self.run_settings else "Manager.TFrame")
            actions.grid(row=row, column=0, columnspan=3 if parent is self.run_settings else 1, sticky="e", pady=(16, 0))
            for column, action in enumerate(names):
                style = "Manager.Primary.TButton" if action in {"start", "test-sources"} else "Manager.TButton"
                button = ttk.Button(actions, text=_ACTION_LABELS[action], style=style,
                                    command=lambda selected=action: self._dispatch(selected))
                button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
                actions.columnconfigure(column, weight=1)
                self.action_buttons[action] = button

    def _build_error(self, parent):
        self.error_frame = ttk.LabelFrame(parent, text="İşlem sonucu / çözüm", padding=10)
        self.error_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.error_frame.columnconfigure(0, weight=1)
        self._label(self.error_frame, textvariable=self.error_var, style="Manager.TLabel").grid(row=0, column=0, sticky="ew")
        bar = ttk.Frame(self.error_frame)
        bar.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.retry_button = ttk.Button(bar, text="Yeniden dene", command=self._retry)
        self.retry_button.grid(row=0, column=0, sticky="w")
        ttk.Button(bar, text="Kaynakları değiştir", command=self._show_sources).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(bar, text="Çözümü incele", command=lambda: self.tabs.select(self.report_tab)).grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.error_frame.grid_remove()

    def _pick(self, key, kind):
        options = {"parent": self.root, "title": self._field_titles[key]}
        if kind == "directory":
            value = filedialog.askdirectory(**options, mustexist=(key != "output"))
        else:
            patterns = {"certificate": [("PEM / sertifika", "*.pem *.crt *.cer"), ("Tüm dosyalar", "*")],
                        "environment": [("Ortam dosyası", ".env *.env *.env.*"), ("Tüm dosyalar", "*")],
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
        if error.field in self._advanced_fields:
            self._set_advanced(True)
        field = self._fields.get(error.field)
        if field:
            self.root.update_idletasks()
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
        width = max(120, event.width)
        if int(event.widget.cget("wraplength")) != width:
            event.widget.configure(wraplength=width)

    def _layout_changed(self, event):
        if event.widget is self.root:
            self._fit_layout()
            if self.state.error_message:
                self.error_var.set(self._error_summary())

    def _fit_layout(self):
        # Reserve useful form/report space on smaller displays and at large
        # system font sizes. The operator can still expand the list explicitly.
        compact = self.root.winfo_height() < max(700, self._section_font.metrics("linespace") * 38)
        compact = compact or bool(self.state.error_message)
        if compact != self._compact_layout:
            self._compact_layout = compact
            self._set_task_details(not compact)

    def _error_summary(self):
        """Keep recovery controls visible; the report retains the complete error."""
        message = self.state.error_message
        summary = message.splitlines()[0][:100]
        width = max(240, self.root.winfo_width() - 100)
        while summary and self._section_font.measure(summary + "…") > width:
            summary = summary[:-1]
        return summary + ("…" if summary != message else "")

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
        self.banner_stop_button.configure(state=str(self.stop_button['state']))
        self.retry_button.configure(state="normal" if self.state.last_action else "disabled")
        self.open_button.configure(state="normal" if self.state.ready_url else "disabled")
        self.report_open_button.configure(state="normal" if self.state.ready_url else "disabled")
        if self.state.ready_url:
            self.open_button.grid()
            self.action_buttons['start'].grid_remove()
        else:
            self.open_button.grid_remove()
            self.action_buttons['start'].grid()
        self.profile_help_var.set("Dev: yerel geliştirme sunucuları; host 127.0.0.1 ile sınırlıdır." if profile == "dev" else "Prod: HTTPS, sabit IPv4 ve ayrı özel veritabanı / artifact dizinleri.")
        self.source_help_var.set({
            "online": "İnternet kaynakları kullanılır. İsteğe bağlı kurumsal ve çevrimdışı yedek kaynaklar aşağıdan seçilebilir.",
            "corporate": "Açıkça belirttiğiniz kurumsal HTTPS depoları veya yerel paket dizinleri kullanılır. CA dosyasını gerekiyorsa seçin.",
            "offline": "Ağ kullanılmaz. Doğrulanmış uygulama bağımlılıklarını içeren çevrimdışı paket dizini zorunludur.",
        }.get(mode, "Kaynak modu seçin."))
        self._update_summary()

    def _update_summary(self):
        """Display controller-owned selection, never infer health from the form."""
        tasks = self.task_states.tasks
        active = sum(task["status"] in ManagerTaskStates.ACTIVE_STATUSES for task in tasks.values())
        self.task_count_var.set(f"{active} aktif · {len(tasks)} işlem" if tasks else "Henüz işlem yok")
        selected = tasks.get(self.selected_task_id())
        if not selected:
            self.summary_title_var.set("Genel bildirimler" if self.state.error_message else "İşlem bekleniyor")
            self.summary_context_var.set("Bir profil seçip işlem başlatın. Durum ve rapor için aşağıdaki listeden bir işlem seçebilirsiniz.")
            return
        action = _ACTION_LABELS.get(selected["action"], safe_text(selected["action"], limit=80))
        status = _TASK_STATUSES.get(selected["status"], "Bilinmiyor")
        self.summary_title_var.set(f"{action} — {status}")
        profile = {"dev": "Geliştirme (dev)", "prod": "Üretim (prod)"}.get(selected["profile"], safe_text(selected["profile"], limit=30))
        self.summary_context_var.set(f"{profile} · İşlem #{safe_text(selected['id'], limit=8)}")

    def set_busy(self, busy: bool):
        """Compatibility hook; input controls remain usable during operations."""
        self.state.busy = bool(busy)
        self._refresh()

    def _refresh(self):
        if self.state.busy != self._progress_running:
            if self.state.busy:
                self.progress.grid()
                self.progress.start(15)
            else:
                self.progress.stop()
                self.progress.grid_remove()
            self._progress_running = self.state.busy
        self.status_var.set(self.state.status)
        if self.state.error_message:
            # Full sanitized error/remedy/code remain in the selectable report.
            self.error_var.set(self._error_summary())
            self.error_frame.grid()
        else:
            self.error_var.set("")
            self.error_frame.grid_remove()
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", self.state.report())
        self.report_text.configure(state="disabled")
        self._update_controls()
        self._fit_layout()

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
