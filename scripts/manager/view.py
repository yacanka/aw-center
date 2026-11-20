"""Native Turkish desktop view; all installation work belongs to the controller."""

from __future__ import annotations

from pathlib import Path
import re
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
from threading import Thread
from typing import Callable
import webbrowser

from .view_model import (DEFAULT_VALUES, PROFILE_OVERRIDE_FIELDS, FormError, ManagerTaskStates,
                         normalize_values, safe_text, validate_admin)
from .task_policy import ACTION_LABELS
from .view_theme import apply_control_styles, icon_image


_ACTION_LABELS = {**ACTION_LABELS,
                  "test-sources": "Kaynakları dene", "bundle": "Çevrimdışı paket hazırla"}
_TASK_STATUSES = {"running": "Çalışıyor", "ready": "Hazır / çalışıyor", "stopping": "Durduruluyor",
                  "degraded": "Sağlık sorunu",
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
        self.canvas.configure(yscrollincrement=12)
        self._wheel_remainder = 0.0
        self._windowing_system = self.tk.call("tk", "windowingsystem")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Manager.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        # The quiet scrollbar lives in the content gutter, so it does not shift
        # every card off the reference's symmetric 30px alignment.
        scrollbar.place(relx=1, x=-5, y=0, anchor="ne", relheight=1,
                        width=int(ttk.Style(self).lookup("Manager.Vertical.TScrollbar", "arrowsize")))
        self.body = ttk.Frame(self.canvas, padding=(28, 27), style="Manager.TFrame")
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
        number = getattr(event, "num", None)
        if number in (4, 5):
            movement = -3 if number == 4 else 3
        else:
            delta = getattr(event, "delta", 0)
            movement = -delta if self._windowing_system == "aqua" else -delta / 120 * 3
        self._wheel_remainder += movement
        units = int(self._wheel_remainder)
        self._wheel_remainder -= units
        if units:
            self.canvas.yview_scroll(units, "units")
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

    _advanced_fields = frozenset({"profile", "source_root", "host", "backend_port", "tls_cert_file", "tls_key_file",
                                  "frontend_port", "install_node",
                                  "install_python", "python_command", "node_command", "env_file"})

    def __init__(self, root, on_action: Callable, on_stop: Callable,
                 on_close: Callable, source_root=None, *, initial_values=None):
        self.root = root
        self.on_action = on_action
        self.on_stop = on_stop
        self.task_states = ManagerTaskStates()
        self.on_open: Callable | None = None
        self.on_inspect = self.on_exit = None
        self._inspection_job = None
        self._admin_dialogs: dict[str, dict] = {}
        self._progress_running = False
        self._refresh_job = None
        self._rendered_report = None
        self._rendered_controls = None
        self._rendered_status_tile = None
        self._error_editing_field = ''
        values = {**DEFAULT_VALUES, **(initial_values or {})}
        self._editing_profile = values['profile']
        self._profile_overrides = {
            profile: {key: values.get(f'{profile}_{key}', '') for key in PROFILE_OVERRIDE_FIELDS}
            for profile in ('dev', 'prod')}
        self.variables = {key: (tk.BooleanVar(root, value=value) if isinstance(value, bool)
                                else tk.StringVar(root, value=value))
                          for key, value in values.items() if key in DEFAULT_VALUES}
        from .paths import default_source_root
        self._default_source_root = str(source_root or default_source_root())
        self._detected_sources: dict[str, str] = {}
        self.variables["source_root"].set(self._default_source_root)
        self._controls: list[ttk.Widget] = []
        self._fields: dict[str, ttk.Entry] = {}
        self._field_titles: dict[str, str] = {}
        self._field_rows: dict[str, list[ttk.Widget]] = {}
        self._pickers: dict[str, ttk.Button] = {}
        self._field_tabs: dict[str, ttk.Frame] = {}
        self._wrapping: list[ttk.Label] = []
        self.status_var = tk.StringVar(root, value=self.state.status)
        self.error_var = tk.StringVar(root)
        self.error_remedy_var = tk.StringVar(root)
        self.source_help_var = tk.StringVar(root)
        self.source_path_var = tk.StringVar(root)
        self._update_source_path()
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
        self.variables['source_root'].trace_add('write', lambda *_: self._source_changed())
        self.variables['validation_policy'].trace_add('write', lambda *_: self._policy_changed())
        self.variables["source_mode"].trace_add("write", lambda *_: self._update_controls())
        self.variables["install_python"].trace_add("write", lambda *_: self._update_controls())
        self.variables["install_node"].trace_add("write", lambda *_: self._update_controls())
        root.bind("<Control-r>", lambda _event: self._retry())
        for number, tab in enumerate((self.run_tab, self.source_tab, self.report_tab), start=1):
            root.bind(f"<Control-Key-{number}>", lambda _event, selected=tab: self.tabs.select(selected))
        for key in (self._advanced_fields | {'assets', 'feature_catalog'}) - {'profile', 'source_root', 'validation_policy'}:
            self.variables[key].trace_add('write', lambda *_: self._update_controls())
        self._update_controls()
        self.root.after(1000, self._tick_progress)

    def _schedule_inspection(self):
        if self._inspection_job is not None:
            self.root.after_cancel(self._inspection_job)
        def inspect():
            self._inspection_job = None
            if self.on_inspect:
                self.on_inspect()
        self._inspection_job = self.root.after(250, inspect)

    def _source_changed(self):
        self.variables['validation_policy'].set('developer')
        self.variables['source_selection'].set('explicit' if self.variables['source_root'].get().strip() else 'automatic')
        self._detected_sources.clear()
        self._update_source_path()
        self._update_controls()
        self._schedule_inspection()

    def _policy_changed(self):
        self._update_controls()
        self._schedule_inspection()

    def _update_source_path(self, detected_source=None):
        """Display worker-resolved paths without doing filesystem work on Tk."""
        selected = self.variables['source_root'].get().strip()
        source = selected or self._default_source_root
        if self.variables['source_selection'].get() == 'automatic':
            profile = self.variables['profile'].get()
            if detected_source:
                self._detected_sources[profile] = detected_source
            source = self._detected_sources.get(profile, source)
        self.source_path_var.set('Kullanılacak kaynak: ' + safe_text(source, limit=8192))

    def _tick_progress(self):
        import time
        state = self._visible_state()
        if state and state.busy:
            elapsed = max(0, int(time.monotonic() - state.started_at))
            self.status_var.set(f'{state.status} · {elapsed // 60:02d}:{elapsed % 60:02d}')
        self.root.after(1000, self._tick_progress)

    def form_values(self, *, include_profiles=False):
        """Snapshot the current form. Only preference storage needs both profiles."""
        values = {key: variable.get() for key, variable in self.variables.items()}
        if include_profiles:
            for profile, overrides in self._profile_overrides.items():
                inputs = values if profile == self._editing_profile else overrides
                values.update({f'{profile}_{key}': inputs[key] for key in PROFILE_OVERRIDE_FIELDS})
        return values

    def form_values_for(self, profile):
        values = self.form_values()
        if profile != values['profile']:
            values.update(self._profile_overrides[profile], profile=profile)
        return values

    @property
    def state(self):
        return self.task_states.current

    def _visible_state(self):
        """Main feedback follows its profile; Details follows the selected report."""
        if self.tabs.select() != str(self.run_tab):
            return self.state
        profile = self.variables['profile'].get()
        general = self.task_states.general
        if (self.selected_task_id() is None and general.error_message
                and general.last_values.get('profile', 'dev') == profile):
            return general
        task_id = self.task_states.profile_presentation(profile)['task_id']
        if task_id:
            return self.task_states.states[task_id]
        for task in reversed(list(self.task_states.tasks.values())):
            if task['profile'] == profile and task['action'] in {'ensure', 'start', 'provision'}:
                return self.task_states.states[task['id']]
        return None

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
        self._palette = {"background": background, "surface": surface, "foreground": foreground,
                         "muted": muted, "border": border, "accent": accent, "soft": soft,
                         "primary": "#2aa675" if dark_surface else "#147d53",
                         "on_primary": "#071e14" if dark_surface else "#ffffff"}
        chrome = "#1c1f22" if dark_surface else "#fafbfc"
        default_font = font.nametofont("TkDefaultFont")
        # A peer system font is a stable baseline across Tk builds. Assuming a
        # platform-specific point size shrinks the reference on some runtimes.
        baseline = max(1, abs(font.nametofont("TkTextFont").cget("size")))
        scale = max(1, abs(default_font.cget("size")) / baseline) * float(self.root.tk.call("tk", "scaling")) * .75
        self._text_scale = max(.75, scale)

        def role_font(pixels, *, weight="normal", fixed=False):
            result = font.nametofont("TkFixedFont" if fixed else "TkDefaultFont").copy()
            result.configure(size=-round(pixels * self._text_scale), weight=weight)
            return result

        self._body_font = role_font(13)
        self._small_font = role_font(12)
        self._eyebrow_font = role_font(11)
        self._mono_font = role_font(12, fixed=True)
        self._heading_font = role_font(25, weight="bold")
        self._section_font = role_font(16, weight="bold")
        # Clam provides paintable ttk elements on Windows too; native Vista
        # elements otherwise ignore the mockup's surfaces and control colors.
        style.theme_use("clam")
        style.configure("TFrame", background=background)
        style.configure("TLabel", background=background, foreground=foreground, font=self._body_font)
        for name, color in (("Manager.TFrame", background), ("Manager.Panel.TFrame", surface)):
            style.configure(name, background=color)
        style.configure("Manager.Chrome.TFrame", background=chrome)
        style.configure("Manager.Divider.TSeparator", background=border)
        style.configure("Manager.Card.TFrame", background=surface, bordercolor=border)
        style.configure("Manager.TLabel", background=background, foreground=foreground)
        style.configure("Manager.Title.TLabel", background=background, foreground=foreground, font=self._heading_font)
        style.configure("Manager.Panel.TLabel", background=surface, foreground=foreground)
        style.configure("Manager.Muted.TLabel", background=background, foreground=muted)
        style.configure("Manager.PanelMuted.TLabel", background=surface, foreground=muted)
        style.configure("Manager.Eyebrow.TLabel", background=background, foreground=muted, font=self._eyebrow_font)
        style.configure("Manager.Badge.TLabel", background=surface, foreground=muted, font=self._eyebrow_font, padding=(8, 4))
        style.configure("Manager.Endpoint.TLabel", background=surface, foreground=muted, font=self._mono_font)
        style.configure("Manager.Brand.TLabel", background=chrome, foreground=foreground, font=self._body_font)
        style.configure("Manager.Section.TLabel", background=surface, foreground=foreground, font=self._section_font)
        style.configure("Manager.TCheckbutton", background=surface, padding=(0, 4), font=self._body_font)
        style.map("Manager.TCheckbutton", background=[("active", surface)])
        style.configure("Manager.Source.TRadiobutton", background=surface, foreground=foreground,
                        font=self._body_font, padding=(0, 5))
        style.map("Manager.Source.TRadiobutton", background=[("active", surface)], foreground=[("disabled", muted)])
        style.configure("Manager.Treeview", rowheight=max(32, self._body_font.metrics("linespace") + 14), font=self._body_font)
        style.configure("Manager.Treeview.Heading", font=self._small_font)
        style.configure("Manager.Treeview", background=surface, fieldbackground=surface,
                        foreground=foreground, borderwidth=0)
        style.configure("Manager.Treeview.Heading", background=surface, foreground=muted,
                        relief="flat", padding=(10, 8))
        style.map("Manager.Treeview", background=[("selected", soft)], foreground=[("selected", foreground)])
        style.configure("Manager.Vertical.TScrollbar", background=border, troughcolor=background,
                        bordercolor=background, lightcolor=border, darkcolor=border,
                        arrowsize=max(8, round(8 * self._text_scale)), borderwidth=0)
        style.layout("Manager.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": 1, "sticky": "nswe"})]})])
        style.configure("Manager.TNotebook", background=background, borderwidth=0,
                        tabmargins=(30, 0, 0, 0))
        self._tab_images = []
        for selected in (False, True):
            image = tk.PhotoImage(master=self.root, width=256, height=48)
            image.put(background, to=(0, 0, 256, 48))
            if selected:
                image.put(accent, to=(0, 46, 256, 48))
            self._tab_images.append(image)
        tab_element = f"Manager.tab.{id(self)}"
        style.element_create(tab_element, "image", self._tab_images[0],
                             ("selected", self._tab_images[1]), border=(0, 0, 0, 2),
                             width=0, height=0, sticky="nsew")
        spacer = tk.PhotoImage(master=self.root, width=1, height=1)
        self._tab_images.append(spacer)
        spacer_element = f"Manager.tabgap.{id(self)}"
        # ttk tiles image elements; stretching this transparent 1px spacer
        # produced thousands of native redraws for every tab repaint.
        style.element_create(spacer_element, "image", spacer, sticky="",
                             padding=(0, 0, round(25 * self._text_scale), 0))
        style.layout("Manager.TNotebook.Tab", [(spacer_element, {"sticky": "nsew", "children": [
            (tab_element, {"sticky": "nsew", "children": [
                ("Notebook.padding", {"sticky": "nsew", "children": [
                    ("Notebook.focus", {"sticky": "nsew", "children": [("Notebook.label", {"sticky": "nsew"})]})]})]})]})])
        style.configure("Manager.TNotebook.Tab", padding=(0, 13, 0, 12), font=self._body_font,
                        foreground=muted, background=background, focuscolor=accent, focusthickness=1)
        style.map("Manager.TNotebook.Tab", foreground=[("selected", accent)])
        self._control_images = apply_control_styles(
            self.root, style, self._palette, body_font=self._body_font, medium_font=self._body_font)

    def _build(self):
        self._configure_styles()
        shell = ttk.Frame(self.root, style="Manager.TFrame")
        shell.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        header = ttk.Frame(shell, padding=(18, 10), height=round(49*self._text_scale), style="Manager.Chrome.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(0, weight=0)
        header.columnconfigure(1, weight=1)
        mark_size = round(27 * self._text_scale)
        mark = tk.Canvas(header, width=mark_size, height=mark_size,
                         background=ttk.Style(self.root).lookup('Manager.Chrome.TFrame', 'background'),
                         borderwidth=0, highlightthickness=0, takefocus=False)
        mark.grid(row=0, column=0, sticky="w", padx=(0, 10))
        radius = round(7 * self._text_scale)
        mark.create_polygon(radius, 0, mark_size-radius, 0, mark_size, 0, mark_size, radius,
                            mark_size, mark_size-radius, mark_size, mark_size, mark_size-radius, mark_size,
                            radius, mark_size, 0, mark_size, 0, mark_size-radius, 0, radius, 0, 0,
                            smooth=True, fill=self._palette['primary'], outline='')
        mark.create_text(mark_size / 2, mark_size / 2, text="AW", fill=self._palette['on_primary'], font=self._eyebrow_font)
        ttk.Label(header, text="Center Manager", style="Manager.Brand.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Separator(header, style="Manager.Divider.TSeparator").place(relx=0, rely=1, relwidth=1, anchor="sw", height=1)
        style = ttk.Style(self.root)
        style.layout('Manager.Single.TNotebook.Tab', [])
        self.tabs = ttk.Notebook(shell, style="Manager.Single.TNotebook")
        self.tabs.grid(row=1, column=0, sticky="nsew")
        self.run_tab = _ScrollPanel(self.tabs)
        self.source_tab = _ScrollPanel(self.tabs)
        self.report_tab = ttk.Frame(self.tabs, padding=14, style="Manager.Panel.TFrame")
        self._tab_icon_images = [
            (icon_image(self.root, name, self._palette['muted'], size=round(16*self._text_scale)),
             icon_image(self.root, name, self._palette['accent'], size=round(16*self._text_scale)))
            for name in ('play', 'package', 'file-text')]
        for panel, text in ((self.run_tab, "Çalışma"), (self.source_tab, "Paket kaynakları"),
                            (self.report_tab, "Ayrıntılar")):
            self.tabs.add(panel, text=text, compound="left")
        self.tabs.bind('<<NotebookTabChanged>>', self._tab_changed)
        self._tab_changed()
        self._build_run(self.run_tab.body)
        self._build_sources(self.source_tab.body)
        self._build_report(self.report_tab)
        self._build_actions()
        self._build_error(shell)
        self._navigation_buttons = []
        for column, (label, panel) in enumerate((('Ana ekran', self.run_tab), ('Kaynaklar', self.source_tab), ('Ayrıntılar', self.report_tab)), 2):
            button = ttk.Button(header, text=label, command=lambda target=panel: self.tabs.select(target),
                                style='Manager.Footer.TButton')
            button.grid(row=0, column=column, padx=(8, 0))
            self._navigation_buttons.append(button)
            if panel is self.report_tab:
                self.details_button = button
        footer = ttk.Frame(shell, padding=(30, 8, 30, 10), style="Manager.TFrame")
        footer.grid(row=4, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, mode="indeterminate", takefocus=False)
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.progress.grid_remove()
        controls = ttk.Frame(footer, style="Manager.TFrame")
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)
        self._label(controls, textvariable=self.status_var, style="Manager.Muted.TLabel").grid(row=0, column=0, sticky="ew", padx=(0, 12))
        ttk.Button(controls, text='Çıkış', command=lambda: self.on_exit() if self.on_exit else None,
                   style='Manager.Footer.TButton').grid(row=0, column=1, padx=(8, 0))

    def _build_tasks(self, parent):
        tasks = self.tasks_card = _Card(parent, padding=12)
        tasks.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        tasks.columnconfigure(0, weight=1)
        bar = ttk.Frame(tasks, style="Manager.Panel.TFrame")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, text="İşlemler", style="Manager.Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(bar, textvariable=self.task_count_var, style="Manager.Panel.TLabel").grid(row=0, column=1, padx=12)
        self.task_tree = ttk.Treeview(tasks, columns=("id", "action", "profile", "status", "report"),
                                      displaycolumns=("action", "profile", "status", "report"),
                                      show="headings", height=1, selectmode="browse", style="Manager.Treeview")
        for key, label, width in (("id", "İşlem no", 80), ("action", "İşlem", 320), ("profile", "Profil", 120), ("status", "Durum", 160), ("report", "Rapor", 85)):
            self.task_tree.heading(key, text=label)
            self.task_tree.column(key, width=width, minwidth=60)
        self.task_tree.grid(row=1, column=0, sticky="ew")
        self.task_scrollbar = ttk.Scrollbar(tasks, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=self.task_scrollbar.set)
        self.task_scrollbar.grid(row=1, column=1, sticky="ns")
        self.task_tree.bind("<<TreeviewSelect>>", self._select_task)
        self.task_tree.bind("<Double-1>", lambda _event: self.tabs.select(self.report_tab))
        self.task_tree.bind("<Return>", lambda _event: self.tabs.select(self.report_tab))
        self.task_tree.bind("<ButtonRelease-1>", self._open_task_report)
        self.stop_button = ttk.Button(bar, text="İşlemi durdur", command=self._stop_selected, state="disabled")
        self.stop_button.grid(row=0, column=2)
        tasks.grid_remove()

    def _tab_changed(self, _event=None):
        selected = self.tabs.select()
        for tab, (normal, active) in zip(self.tabs.tabs(), self._tab_icon_images):
            self.tabs.tab(tab, image=active if tab == selected else normal)
        if hasattr(self, "report_text") and selected == str(self.report_tab):
            self._render_report()
        if hasattr(self, 'action_buttons'):
            self._update_settings(self._profile_presentation()['status'])
            self._refresh()

    def _open_task_report(self, event):
        if self.task_tree.identify_region(event.x, event.y) != "cell" or self.task_tree.identify_column(event.x) != "#4":
            return
        task_id = self.task_tree.identify_row(event.y)
        if task_id in self.task_states.tasks:
            self.task_states.select(task_id)
            self._sync_task_selection()
            self._refresh()
            self.tabs.select(self.report_tab)
            self._render_report()

    def _entry(self, parent, row, key, label, *, tab, picker=None, stacked=False):
        title = ttk.Label(parent, text=label, style="Manager.Panel.TLabel")
        title.grid(
            row=row-1 if stacked else row, column=0, columnspan=3 if stacked else 1,
            sticky="w", padx=(0, 12), pady=(0, 6) if stacked else 7)
        entry = ttk.Entry(parent, textvariable=self.variables[key], width=32)
        entry.grid(row=row, column=0 if stacked else 1, columnspan=2 if stacked else 1, sticky="ew", pady=7)
        self._fields[key] = entry
        self._field_titles[key] = label
        self._field_rows[key] = [title, entry]
        self._field_tabs[key] = tab
        self._controls.append(entry)
        if picker:
            caption = "Çevrimdışı paket seç…" if key == "offline_dir" else "Seç…"
            button = ttk.Button(parent, text=caption, command=lambda: self._pick(key, picker))
            button.grid(row=row, column=2, sticky="ew", padx=(8, 0), pady=7)
            self._pickers[key] = button
            self._field_rows[key].append(button)
            self._controls.append(button)
        parent.columnconfigure(1, weight=1)
        return entry

    def _build_run(self, parent):
        parent.columnconfigure(0, weight=1)
        summary = _Card(parent)
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        summary.columnconfigure(1, weight=1)
        tile_size = round(42 * self._text_scale)
        self.status_tile = tk.Canvas(summary, width=tile_size, height=tile_size,
                                     borderwidth=0, highlightthickness=0, takefocus=False,
                                     background=self._palette['surface'])
        self.status_tile.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 15))
        self._label(summary, textvariable=self.summary_title_var, style="Manager.Section.TLabel").grid(row=0, column=1, sticky="ew")
        self._label(summary, textvariable=self.summary_context_var, style="Manager.Endpoint.TLabel").grid(row=1, column=1, sticky="ew", pady=(5, 0))
        self.banner_actions = ttk.Frame(summary, style="Manager.Panel.TFrame")
        self.banner_actions.grid(row=2, column=1, sticky="w", pady=(14, 0))
        self.banner_stop_button = ttk.Button(self.banner_actions, text="Durdur", command=self._stop_profile,
                                             style="Manager.TButton", state="disabled")
        self.banner_stop_button.grid(row=0, column=1, padx=(8, 0))
        self.copy_address_button = ttk.Button(self.banner_actions, command=self._copy_ready_address)
        self.copy_address_button.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        profile = ttk.Frame(summary, style="Manager.Segment.TFrame", padding=3)
        profile.grid(row=0, column=2, rowspan=2, sticky="ne")
        for column, (value, label) in enumerate((("dev", "Geliştirme"), ("prod", "Üretim"))):
            button = ttk.Radiobutton(profile, text=label, value=value, variable=self.variables["profile"], style="Manager.TRadiobutton")
            button.grid(row=0, column=column)
            self._controls.append(button)
        paths = self.run_settings = _Card(parent, padding=20)
        paths.grid(row=3, column=0, sticky="ew")
        paths.columnconfigure(0, weight=1)
        ttk.Label(paths, text="Çalışma ayarları", style="Manager.Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        source = ttk.Frame(paths, style="Manager.Panel.TFrame")
        source.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        source.columnconfigure(1, weight=1)
        self.source_path_label = self._label(source, textvariable=self.source_path_var, style='Manager.Muted.TLabel')
        self.source_path_label.grid(row=3, column=0, columnspan=3, sticky='ew')
        self._entry(source, 1, "source_root", "Proje kaynak dizini", tab=self.run_tab, picker="directory", stacked=True)
        self._label(source, "Kayıtlı kurulumu kullanmak için boş bırakın. Git deposunu seçmek depodaki sürümü seçer; kurulu prod'u otomatik güncellemez.",
                    style="Manager.Muted.TLabel").grid(row=2, column=0, columnspan=3, sticky="ew")
        connection = ttk.Frame(paths, style="Manager.Panel.TFrame")
        connection.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for column, (key, title) in enumerate((("host", "Sunucu adresi"), ("backend_port", "Sunucu portu"))):
            connection.columnconfigure(column, weight=1, uniform="connection")
            field = ttk.Frame(connection, style="Manager.Panel.TFrame")
            field.grid(row=0, column=column, sticky="ew", padx=(0, 8) if column == 0 else (8, 0))
            field.columnconfigure(0, weight=1)
            label = ttk.Label(field, text=title, style="Manager.Panel.TLabel")
            label.grid(row=0, column=0, sticky="w", pady=(0, 6))
            if key == 'host':
                self.host_label = label
            entry = ttk.Entry(field, textvariable=self.variables[key], width=12)
            entry.grid(row=1, column=0, sticky="ew")
            self._fields[key], self._field_titles[key], self._field_tabs[key] = entry, title, self.run_tab
            self._controls.append(entry)
        connection_help = self._label(paths, "Boş alanlarda .env veya profil varsayılanları kullanılır. Geliştirme portu için auto girebilirsiniz.", style="Manager.PanelMuted.TLabel")
        connection_help.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.tls_frame = ttk.Frame(paths, style='Manager.Panel.TFrame')
        self.tls_frame.grid(row=4, column=0, columnspan=3, sticky='ew')
        self._entry(self.tls_frame, 0, 'tls_cert_file', 'TLS sertifikası', tab=self.run_tab, picker='certificate')
        self._entry(self.tls_frame, 1, 'tls_key_file', 'TLS özel anahtarı', tab=self.run_tab, picker='key')
        self.advanced_button = ttk.Button(parent, text="Ayarlar", command=self._toggle_advanced,
                                          style="Manager.Link.TButton")
        self.advanced_button.grid(row=2, column=0, sticky="w", pady=(0, 12))
        self.advanced_frame = ttk.Frame(paths, style="Manager.Panel.TFrame")
        self.advanced_frame.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self._build_advanced(self.advanced_frame)
        self._optional_rows = (profile, source, self._fields['backend_port'].master, connection_help, self.advanced_frame)

    def _build_advanced(self, parent):
        self.validation_selector = ttk.Checkbutton(
            parent, text='Açılışta kapsamlı denetimleri çalıştır',
            variable=self.variables['validation_policy'], onvalue='managed', offvalue='developer',
            style='Manager.TCheckbutton')
        self.validation_selector.grid(row=18, column=0, columnspan=3, sticky='w', pady=(8, 0))
        self._controls.append(self.validation_selector)
        self._fields['validation_policy'] = self.validation_selector
        self._field_tabs['validation_policy'] = self.run_tab
        self._entry(parent, 0, "frontend_port", "Frontend portu (dev)", tab=self.run_tab)
        self.production_help = self._label(parent, "Yeni prod profili için makineye atanmış sabit IPv4 ve kaynak dizini dışındaki TLS dosyaları gerekir.")
        self.production_help.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        python = ttk.Checkbutton(parent, text="Her durumda yönetilen Python kurulumunu kullan",
                                 variable=self.variables['install_python'], style="Manager.TCheckbutton")
        python.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._controls.append(python)
        self._label(parent, "Varsayılan olarak önce sistemdeki CPython 3.11 x64 aranır; bulunamazsa yönetilen Python otomatik indirilir veya çevrimdışı paketten kurulur. Bu seçim yönetilen kurulumu zorlar. pip paketleri ayrı sanal ortama kurulur.").grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        self._entry(parent, 7, 'python_command', 'Python komutu / yolu (isteğe bağlı)', tab=self.run_tab, picker='python')
        python_help = self._label(parent, 'Boşsa otomatik aranır. python, py -3.11, python.exe dosyasının tam yolu veya kurulum dizini girilebilir. Başlat ve durum kontrolü kayıtlı profilin Python seçimini kullanır.')
        python_help.grid(row=8, column=0, columnspan=3, sticky='ew', pady=(4, 12))
        self._field_rows['python_command'].append(python_help)
        self._entry(parent, 9, 'node_command', 'Node.js komutu / yolu (isteğe bağlı)', tab=self.run_tab, picker='node')
        managed_node = ttk.Checkbutton(parent, text='Her durumda yönetilen Node.js kurulumunu kullan',
                                      variable=self.variables['install_node'], style='Manager.TCheckbutton')
        managed_node.grid(row=14, column=0, columnspan=3, sticky='w', pady=(8, 0))
        self._controls.append(managed_node)
        node_help = self._label(parent, 'Boşsa önce uygun sistem Node.js aranır; bulunamazsa yönetilen Node.js kurulur. node, node.exe dosyasının tam yolu veya kurulum dizini girilebilir. Başlat ve durum kontrolü kayıtlı profilin Node.js seçimini kullanır.')
        node_help.grid(row=10, column=0, columnspan=3, sticky='ew', pady=(4, 12))
        self._field_rows['node_command'].append(node_help)
        self._entry(parent, 11, 'env_file', '.env dosyası (isteğe bağlı)', tab=self.run_tab, picker='environment')
        self._label(parent, 'AW Center’ı aç seçilen dosyadaki uygulama ayarlarını her açılışta okur; kaynak dosyayı değiştirmez. Manager’a girdiğiniz değerler .env değişse de geçerlidir. Alanı temizlemek .env değerini, orada da yoksa varsayılanı kullanır.').grid(row=12, column=0, columnspan=3, sticky='ew', pady=(4, 0))

    def _set_advanced(self, expanded: bool):
        self.advanced_var.set(expanded)
        self.advanced_button.configure(text="Ayarları kapat" if expanded else "Ayarlar")
        self._update_settings(self._profile_presentation()['status'])

    def _update_settings(self, status):
        expanded = self.advanced_var.get()
        new_production = self.variables['profile'].get() == 'prod' and status == 'not_installed'
        self.run_settings.grid() if expanded or new_production else self.run_settings.grid_remove()
        for button in self._navigation_buttons:
            button.grid() if expanded or self.tabs.select() != str(self.run_tab) else button.grid_remove()
        for widget in self._optional_rows:
            widget.grid() if expanded else widget.grid_remove()

    def _toggle_advanced(self):
        self._set_advanced(not self.advanced_var.get())

    def _profile_changed(self):
        selected = self.variables['profile'].get()
        if selected != self._editing_profile:
            self._profile_overrides[self._editing_profile] = {
                key: self.variables[key].get() for key in PROFILE_OVERRIDE_FIELDS}
            self._editing_profile = selected
            for key, value in self._profile_overrides[selected].items():
                self.variables[key].set(value)
        self.variables['validation_policy'].set('developer')
        self._update_source_path()
        self._refresh()
        self._schedule_inspection()

    def _build_sources(self, parent):
        parent.columnconfigure(0, weight=1)
        modes = _Card(parent)
        modes.grid(row=0, column=0, sticky="ew")
        ttk.Label(modes, text="Paket kaynakları", style="Manager.Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        for column, (value, label) in enumerate((('restricted', 'Otomatik (önerilen)'), ("online", "Önce internet"), ("corporate", "Yalnız kurumsal"), ("offline", "Çevrimdışı"))):
            button = ttk.Radiobutton(modes, text=label, value=value, variable=self.variables["source_mode"], style="Manager.Source.TRadiobutton")
            button.grid(row=1 + column // 2, column=column % 2, sticky="w", padx=(0, 12), pady=4)
            self._controls.append(button)
        self._label(modes, textvariable=self.source_help_var).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        fields = _Card(parent)
        fields.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        for row, (key, label, picker) in enumerate((
            ("repository", "Arşiv deposu / yerel dizin", "directory"),
            ("offline_dir", "Çevrimdışı paket klasörü", "directory"),
            ("bundle_import", "Runtime arşivi · Dosyadan ekle", "archive"),
            ("python_index_url", "Python paket indeksi (pip)", None),
            ("npm_registry_url", "JavaScript paket deposu (npm)", None),
            ("ca_file", "Kurumsal CA dosyası (PEM)", "certificate"),
            ("assets", "Onaylı asset dizini (isteğe bağlı)", "directory"),
            ("feature_catalog", "Native araç kataloğu (isteğe bağlı)", "catalog"),
            ("output", "Paket çıktı klasörü (boşsa otomatik)", "directory"),
            ('manager_distribution', 'Hazır Windows Manager paketi (isteğe bağlı)', 'directory'),
        )):
            self._entry(fields, row, key, label, tab=self.source_tab, picker=picker)
        options = _Card(parent)
        options.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(options, text="Paket türü · Varsayılan tam offline paket").grid(row=0, column=0, sticky="w")
        for row, (field, label) in enumerate((("bundle_host_python", "Hedefte kurulu Python’u kullan"),
                                              ("bundle_host_node", "Hedefte kurulu Node.js ve npm’i kullan")), 1):
            button = ttk.Checkbutton(options, text=label, variable=self.variables[field])
            button.grid(row=row, column=0, sticky="w")
            self._controls.append(button)


    def _build_report(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        self._build_tasks(parent)
        self._label(parent, "Seçili işlemin güvenli durum raporu.").grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.report_text = tk.Text(parent, wrap="word", width=60, height=12, state="disabled", font=self._body_font, takefocus=True, borderwidth=0, padx=12, pady=12)
        scrollbar = ttk.Scrollbar(parent, command=self.report_text.yview)
        self.report_text.configure(yscrollcommand=scrollbar.set)
        self.report_text.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        # A native Text is needed for selectable reports; derive its appearance from ttk.
        style = ttk.Style(parent)
        for option, style_option in (("background", "fieldbackground"), ("foreground", "foreground")):
            color = style.lookup("TEntry", style_option)
            if color:
                self.report_text.configure(**{option: color})
        bar = self.report_actions = ttk.Frame(parent, style="Manager.Panel.TFrame")
        bar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(bar, text="Güvenli raporu kopyala", command=self._copy_report).grid(row=0, column=0, sticky="w")
        self.report_open_button = ttk.Button(bar, text="Tarayıcıda aç", command=self._open_ready, state="disabled")
        self.report_open_button.grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Button(bar, text='Bildirimler', command=self._show_general).grid(row=0, column=2, padx=(12, 0))

    def _build_actions(self):
        """Place each operation with its inputs; stopping remains task-scoped."""
        self.action_buttons = {"start": ttk.Button(self.banner_actions, text="Başlat", style="Manager.Primary.TButton",
                                                   command=self._primary_action)}
        self.action_buttons["start"].grid(row=0, column=0)
        doctor = ttk.Button(self.report_actions, text=_ACTION_LABELS['doctor'], command=lambda: self._dispatch('doctor'))
        doctor.grid(row=0, column=3, padx=(12, 0))
        self.action_buttons['doctor'] = doctor
        actions = ttk.Frame(self.source_tab.body, style="Manager.Panel.TFrame")
        actions.grid(row=3, column=0, columnspan=3, sticky="e", pady=(16, 0))
        for column, action in enumerate(("test-sources", "bundle")):
            style = "Manager.Primary.TButton" if action == "test-sources" else "Manager.TButton"
            button = ttk.Button(actions, text=_ACTION_LABELS[action], style=style,
                                command=lambda selected=action: self._dispatch(selected))
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
            actions.columnconfigure(column, weight=1)
            self.action_buttons[action] = button

    def _build_error(self, parent):
        self.error_frame = ttk.LabelFrame(parent, text="İşlem tamamlanamadı", padding=10)
        self.error_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.error_frame.columnconfigure(0, weight=1)
        # Keep the controls reachable at large system font sizes. The entire
        # explanation remains selectable and scrollable even on a small screen.
        description = ttk.Frame(self.error_frame)
        description.grid(row=0, column=0, sticky='ew')
        description.columnconfigure(0, weight=1)
        self.error_text = tk.Text(description, height=3, width=1, wrap='word', state='disabled',
                                  font=self._body_font, borderwidth=0, highlightthickness=0,
                                  background=self._palette['background'], foreground=self._palette['foreground'])
        self.error_text.grid(row=0, column=0, sticky='ew')
        scroll = ttk.Scrollbar(description, command=self.error_text.yview, orient='vertical')
        scroll.grid(row=0, column=1, sticky='ns')
        self.error_text.configure(yscrollcommand=scroll.set)
        self.error_field_frame = ttk.Frame(self.error_frame)
        self.error_field_frame.grid(row=2, column=0, sticky='ew', pady=(8, 0))
        self.error_field_frame.columnconfigure(1, weight=1)
        self.error_field_label = ttk.Label(self.error_field_frame)
        self.error_field_label.grid(row=0, column=0, sticky='w', padx=(0, 8))
        self.error_entry = ttk.Entry(self.error_field_frame)
        self.error_entry.grid(row=0, column=1, sticky='ew')
        self.error_picker = ttk.Button(self.error_field_frame, text='Seç…')
        self.error_picker.grid(row=0, column=2, padx=(8, 0))
        self.error_field_frame.grid_remove()
        bar = ttk.Frame(self.error_frame)
        bar.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.retry_button = ttk.Button(bar, text="Yeniden dene", command=self._retry)
        self.retry_button.grid(row=0, column=0, sticky="w")
        self.support_button = ttk.Button(bar, text="Destek bilgisini kopyala", command=self._copy_support)
        self.support_button.grid(row=0, column=1, padx=(8, 0))
        self.error_frame.grid_remove()

    def _set_error_description(self, state):
        message, remedy = state.error_message, state.error_remedy
        if state.error_code in {'production_settings_required', 'tls_file_missing', 'tls_file_unavailable'}:
            instructions = {
                'tls_cert_file': ('Sunucu sertifikası eksik.', 'Sunucu sertifikanızın dosyasını seçin.'),
                'tls_key_file': ('Sertifikanın özel anahtarı eksik.', 'Sunucu sertifikanıza ait özel anahtar dosyasını seçin.'),
                'host': ('Sunucunun ağ adresi eksik.', 'Sunucunun sabit IPv4 adresini girin.'),
            }
            message, remedy = instructions.get(state.error_field, (message, remedy))
        if state.error_code in {'manager_action_failed', 'operation_failed'}:
            message = 'AW Center işlemi tamamlayamadı.'
            remedy = 'Sistem yöneticinizden yardım isteyin. Destek bilgisini kopyala düğmesiyle hata kodunu paylaşabilirsiniz.'
        if (message, remedy) != (self.error_var.get(), self.error_remedy_var.get()):
            self.error_var.set(message)
            self.error_remedy_var.set(remedy)
            self.error_text.configure(state='normal')
            self.error_text.delete('1.0', 'end')
            self.error_text.insert('1.0', message + '\n' + remedy)
            self.error_text.configure(state='disabled')
            self.error_text.yview_moveto(0)

    def _copy_support(self):
        state = self._visible_state()
        if not state or not state.error_message:
            return
        # Free-form event text and the report may contain paths or internal host
        # names. Support needs only the machine code and the affected operation.
        code = state.error_code if re.fullmatch(r'[a-z][a-z0-9_]{0,99}', state.error_code) else 'manager_error'
        description = {'ensure': 'AW Center açılırken işlem tamamlanamadı.',
                       'start': 'AW Center başlatılamadı.', 'provision': 'AW Center kurulumu tamamlanamadı.',
                       'doctor': 'Ortam kontrolü tamamlanamadı.', 'bundle': 'Çevrimdışı paket hazırlanamadı.',
                       'test-sources': 'Paket kaynakları kontrol edilemedi.'}.get(state.last_action, 'İşlem tamamlanamadı.')
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(f'{code}\n{description}')
        except tk.TclError:
            self.status_var.set(f'Panoya erişilemedi. Sistem yöneticinize {code} kodunu bildirin.')
            return
        self.status_var.set('Hata kodu ve kısa açıklama panoya kopyalandı.')

    def _update_error_field(self, state):
        field = state.error_field if state else ''
        original = self._fields.get(field)
        if (not isinstance(original, ttk.Entry) or original.instate(['disabled'])
                or state.last_values.get('profile', 'dev') != self.variables['profile'].get()):
            self._error_editing_field = ''
            self.error_field_frame.grid_remove()
            return
        self.error_field_label.configure(text=self._field_titles[field])
        self.error_entry.configure(textvariable=self.variables[field])
        self.error_field_frame.grid()
        if field in self._pickers:
            caption = {'tls_cert_file': 'Sertifikayı seç', 'ca_file': 'Sertifikayı seç',
                       'tls_key_file': 'Özel anahtarı seç', 'offline_dir': 'Paket klasörünü seç',
                       'env_file': 'Ayar dosyasını seç'}.get(field, self._pickers[field].cget('text'))
            self.error_picker.configure(text=caption, command=self._pickers[field].invoke)
            self.error_picker.grid()
        else:
            self.error_picker.grid_remove()
        if self._error_editing_field != field:
            self.error_entry.focus_set()
        self._error_editing_field = field

    def _pick(self, key, kind):
        options = {"parent": self.root, "title": self._field_titles[key]}
        if kind == "directory":
            value = filedialog.askdirectory(**options, mustexist=(key != "output"))
        else:
            patterns = {"archive": [("Runtime arşivi", "*.zip *.tgz *.tar.gz")], "certificate": [("PEM / sertifika", "*.pem *.crt *.cer"), ("Tüm dosyalar", "*")],
                        "python": [("Python yorumlayıcısı", "python*.exe"), ("Tüm dosyalar", "*")],
                        "node": [("Node.js", "node.exe"), ("Tüm dosyalar", "*")],
                        "environment": [("Ortam dosyası", ".env *.env *.env.*"), ("Tüm dosyalar", "*")],
                        "key": [("PEM / özel anahtar", "*.pem *.key"), ("Tüm dosyalar", "*")],
                        "catalog": [("JSON kataloğu", "*.json"), ("Tüm dosyalar", "*")]}
            value = filedialog.askopenfilename(**options, filetypes=patterns[kind])
        if value:
            self.variables[key].set(value)
            if key == "offline_dir":
                self.variables["source_mode"].set("offline")

    def _dispatch(self, action, values=None):
        try:
            selected = values if values is not None else self.form_values()
            submitted = normalize_values(action, selected)
        except FormError as error:
            self._show_form_error(error, action)
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

    def _show_form_error(self, error, action='ensure'):
        self.task_states.general.last_action = action
        self.task_states.general.last_values = {'profile': self.variables['profile'].get()}
        self.handle_event({"type": "error", "code": "invalid_form", "field": error.field,
                           "message": str(error), "remedy": "Aşağıdaki alanı düzeltip Yeniden dene’ye basın."})

    def _retry(self):
        state = self._visible_state()
        action = state.last_action if state else None
        if not action:
            return
        values = state.last_values
        if action in {'ensure', 'start', 'provision'}:
            action = 'ensure'
            current = self.form_values()
            if current['profile'] == values.get('profile', 'dev'):
                values = current
        elif action == 'bundle' or ((action == 'test-sources' or state.error_field)
                                    and self.variables['profile'].get() == values.get('profile', 'dev')):
            values = self.form_values()
        self._dispatch(action, values)

    def _profile_presentation(self):
        presentation = self.task_states.profile_presentation(self.variables['profile'].get())
        if presentation['action'] == 'open':
            state = self.task_states.states[presentation['task_id']]
            current = normalize_values('start', self.form_values())
            fields = self._advanced_fields | {'validation_policy', 'source_selection', 'assets', 'feature_catalog'}
            if any(current.get(key, DEFAULT_VALUES[key]) != state.last_values.get(key, DEFAULT_VALUES[key])
                   for key in fields):
                return {**presentation, 'action': 'ensure', 'label': 'Durdur, uygula ve aç'}
        return presentation

    def _primary_action(self):
        action = self._profile_presentation()['action']
        if action == 'open':
            self._open_ready()
        elif action:
            self._dispatch(action)

    def _stop_profile(self):
        task = self._profile_presentation()['task_id']
        if task:
            self.on_stop(task)

    def _copy_report(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.state.report())
        except tk.TclError:
            self.status_var.set("Panoya erişilemedi. Rapor sekmesindeki metni seçip kopyalayabilirsiniz.")
            return
        self.status_var.set("Güvenli durum raporu panoya kopyalandı.")

    def _copy_ready_address(self):
        url = self.task_states.profile_presentation(self.variables['profile'].get())['url']
        if not url:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
        except tk.TclError:
            self.status_var.set(f"Adresi tarayıcınıza yazın: {url}")
            return
        self.status_var.set("Bağlantı kopyalandı.")

    def _open_ready(self):
        presentation = self._profile_presentation()
        url = presentation['url']
        if not url:
            return
        if self.on_open:
            self.on_open(url, presentation['task_id'])
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

    def _update_controls(self):
        selected = self.task_states.tasks.get(self.selected_task_id(), {})
        profile_state = self._profile_presentation()
        visible = self._visible_state()
        presentation = (self.variables["profile"].get(), self.variables["source_mode"].get(),
                        self.variables["validation_policy"].get(), self.variables["source_selection"].get(),
                        self.variables['install_python'].get(), selected.get("status"),
                        self.variables['install_node'].get(),
                        bool(visible and visible.last_action), tuple(profile_state.items()))
        if presentation == self._rendered_controls:
            self._update_summary()
            self._paint_status_tile()
            return
        self._rendered_controls = presentation
        for control in self._controls:
            control.configure(state="normal")
        profile = self.variables["profile"].get()
        self._update_settings(profile_state['status'])
        self._field_titles['host'] = 'Sabit IPv4' if profile == 'prod' else 'Sunucu adresi'
        self.host_label.configure(text=self._field_titles['host'])
        self.tls_frame.grid() if profile == 'prod' else self.tls_frame.grid_remove()
        self.production_help.grid() if profile == 'prod' else self.production_help.grid_remove()
        mode = self.variables["source_mode"].get()
        disabled = {"frontend_port"} if profile == "prod" else {"tls_cert_file", "tls_key_file"}
        if self.variables['install_python'].get():
            disabled.add('python_command')
        if self.variables['install_node'].get():
            disabled.add('node_command')
        if mode == "offline":
            disabled.update({"repository", "python_index_url", "npm_registry_url"})
        for key, widgets in self._field_rows.items():
            for widget in widgets:
                widget.grid_remove() if key in disabled else widget.grid()
        for key in disabled:
            self._fields[key].configure(state="disabled")
            if key in self._pickers:
                self._pickers[key].configure(state="disabled")
        for button in self.action_buttons.values():
            button.configure(state="normal")
        selected = self.task_states.tasks.get(self.selected_task_id(), {})
        self.stop_button.configure(state="normal" if selected.get("status") in ManagerTaskStates.ACTIVE_STATUSES else "disabled")
        self.banner_stop_button.configure(state="normal" if profile_state['task_id'] else "disabled")
        self.banner_stop_button.grid() if profile_state['task_id'] else self.banner_stop_button.grid_remove()
        self.retry_button.configure(state="normal" if visible and visible.last_action else "disabled")
        if profile_state['url']:
            self.copy_address_button.configure(text='Ekip bağlantısını kopyala' if profile == 'prod' else 'Adresi kopyala')
            self.copy_address_button.grid()
        else:
            self.copy_address_button.grid_remove()
        self.report_open_button.configure(state="normal" if profile_state['url'] else "disabled")
        self.action_buttons['start'].configure(text=profile_state['label'],
            state="normal" if profile_state['action'] else "disabled")
        self.action_buttons['start'].grid()
        self.source_help_var.set({
            "online": "Doğrulanmış yerel paketler kullanılır; eksikler için önce genel internet, ardından seçilen kurumsal kaynaklar denenir.",
            "restricted": "Önce doğrulanmış yerel paketler, sonra seçilen depolar ve genel internet kaynakları otomatik denenir. Geçici bağlantı hataları yeniden denenir; yalnız çözülemeyen ihtiyaçlar bildirilir.",
            "corporate": "Açıkça belirttiğiniz kurumsal HTTPS depoları veya yerel paket dizinleri kullanılır. CA dosyasını gerekiyorsa seçin.",
            "offline": "Ağ kullanılmaz. EXE yanındaki doğrulanmış paketler otomatik bulunur; başka bir paket dizini de seçebilirsiniz.",
        }.get(mode, "Kaynak modu seçin."))
        self._update_summary()
        self._paint_status_tile()

    def _paint_status_tile(self):
        """Decorative state icon; the adjacent text always explains its meaning."""
        profile = self._profile_presentation()
        state = (profile['status'] in {'blocked', 'degraded'}, bool(profile['url']), bool(profile['task_id']))
        if state == self._rendered_status_tile:
            return
        self._rendered_status_tile = state
        tile, size = self.status_tile, round(42 * self._text_scale)
        tile.delete('all')
        r = size / 4
        tile.create_polygon(r, 0, size-r, 0, size, 0, size, r, size, size-r,
                            size, size, size-r, size, r, size, 0, size, 0, size-r,
                            0, r, 0, 0, smooth=True, fill=self._palette['soft'], outline='')
        color = self._palette['accent']
        tile.create_oval(size*.24, size*.24, size*.76, size*.76, outline=color, width=2)
        if state[0]:
            tile.create_text(size/2, size/2, text='!', font=self._section_font, fill=color)
        elif state[1]:
            tile.create_line(size*.35, size*.5, size*.46, size*.61, size*.67, size*.39,
                             fill=color, width=2, capstyle='round', joinstyle='round')
        elif state[2]:
            tile.create_text(size/2, size/2-2, text='…', font=self._body_font, fill=color)

    def _update_summary(self):
        """The profile dashboard stays independent of the selected task report."""
        tasks = self.task_states.tasks
        active = sum(task["status"] in ManagerTaskStates.ACTIVE_STATUSES for task in tasks.values())
        self.task_count_var.set(f"{active} aktif · {len(tasks)} işlem" if tasks else "Henüz işlem yok")
        current = self._profile_presentation()
        name = 'Geliştirme' if self.variables['profile'].get() == 'dev' else 'Üretim'
        descriptions = {'not_installed': 'kurulumu gerekli', 'stopped': 'profili kayıtlı', 'unverified': 'profili kayıtlı',
            'incomplete': 'kurulumu tamamlanmalı', 'blocked': 'kurulumu engellendi',
            'inspecting': 'ortamı denetleniyor', 'degraded': 'ortamında sağlık sorunu',
            'running': 'işlemi sürüyor', 'finishing': 'işlemi tamamlanıyor', 'stopping': 'ortamı durduruluyor'}
        self.summary_title_var.set(f"{name} {descriptions.get(current['status'], 'ortamı başlatılıyor')}")
        self.summary_context_var.set('')
        if current['url']:
            from urllib.parse import urlsplit
            endpoint = urlsplit(current['url'])
            self.summary_title_var.set(f"{name} ortamı çalışıyor")
            self.summary_context_var.set(f"{endpoint.scheme}://{safe_text(endpoint.netloc, limit=120)}")

        policy = self.variables['validation_policy'].get()
        active = self.task_states.states.get(current['task_id'])
        active_policy = active.last_values.get('validation_policy', 'managed') if active else policy
        label = 'Hızlı kontrol' if active_policy == 'developer' else 'Kapsamlı denetim'
        if active_policy != policy:
            label += ' · Seçim: ' + ('Hızlı kontrol' if policy == 'developer' else 'Kapsamlı denetim')
        self.summary_context_var.set(' · '.join(filter(None, (label, self.summary_context_var.get()))))

    def set_busy(self, busy: bool):
        """Compatibility hook; input controls remain usable during operations."""
        self.state.busy = bool(busy)
        self._refresh()

    def _refresh(self):
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
            self._refresh_job = None
        state = self._visible_state()
        task_id = (self._profile_presentation()['task_id'] if self.tabs.select() == str(self.run_tab)
                   else self.selected_task_id())
        status = self.task_states.tasks.get(task_id, {}).get('status')
        # A ready server remains controller-owned, but its startup has finished.
        # Progress is presentation state and must not change lifecycle fencing.
        progressing = bool(state and state.busy and status not in {'ready', 'degraded'})
        if progressing != self._progress_running:
            if progressing:
                self.progress.grid()
                self.progress.start(15)
            else:
                self.progress.stop()
                self.progress.grid_remove()
            self._progress_running = progressing
        self.status_var.set(state.status if state else '')
        if state and state.error_message:
            self._set_error_description(state)
            self.error_frame.grid()
            self._update_error_field(state)
        else:
            self.error_var.set("")
            self.error_remedy_var.set("")
            self._error_editing_field = ''
            self.error_field_frame.grid_remove()
            self.error_frame.grid_remove()
        if self.tabs.select() == str(self.report_tab):
            self._render_report()
        self._update_controls()

    def _render_report(self):
        report = self.state.report()
        identity = (self.selected_task_id(), report)
        if identity == self._rendered_report:
            return
        same_task = self._rendered_report is not None and self._rendered_report[0] == identity[0]
        position = self.report_text.yview()[0] if same_task else 0
        self._rendered_report = identity
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", report)
        self.report_text.configure(state="disabled")
        self.report_text.yview_moveto(position)

    def handle_event(self, event: dict):
        if (event.get('type') == 'status' and isinstance(event.get('offline_root'), str)
                and isinstance(event.get('selected_offline_dir'), str)
                and self.variables['source_mode'].get() == 'offline'
                and Path(self.variables['offline_dir'].get()) == Path(event['selected_offline_dir'])):
            self.variables['offline_dir'].set(event['offline_root'])
        if event.get('type') == 'error' and event.get('task_id') is None:
            self.task_states.general.last_values['profile'] = self.variables['profile'].get()
        self.task_states.handle_event(event)
        if (event.get('type') == 'profile' and event.get('profile') == self.variables['profile'].get()
                and isinstance(event.get('source_root'), str)):
            self._update_source_path(event['source_root'])
        if (event.get("task_id") is not None and event["task_id"] != self.selected_task_id()
                and event['task_id'] != self._profile_presentation()['task_id']):
            self._update_controls()
            return
        self._sync_task_selection()
        # The model consumes every event immediately. A poll's burst needs one
        # paint, and hidden/background reports must not interrupt operator input.
        if self._refresh_job is None:
            self._refresh_job = self.root.after_idle(self._refresh)

    def selected_task_id(self) -> str | None:
        return self.task_states.selected_id

    def update_tasks(self, tasks: list[dict], selected_id: str | None = None):
        """Render controller-owned lifecycle rows without replacing task reports."""
        self.task_states.update_tasks(tasks, selected_id)
        self.tasks_card.grid() if self.task_states.tasks else self.tasks_card.grid_remove()
        existing = set(self.task_tree.get_children())
        for task_id, task in self.task_states.tasks.items():
            values = (safe_text(task_id, limit=8),
                      _ACTION_LABELS.get(task["action"], safe_text(task["action"], limit=80)),
                      safe_text(task["profile"], limit=30),
                      _TASK_STATUSES.get(task["status"], "Bilinmiyor"), "İncele →")
            if task_id in existing:
                if tuple(self.task_tree.item(task_id, "values")) != values:
                    self.task_tree.item(task_id, values=values)
            else:
                self.task_tree.insert("", "end", iid=task_id, values=values)
        for task_id in existing - self.task_states.tasks.keys():
            self.task_tree.delete(task_id)
        height = max(1, min(2, len(self.task_states.tasks)))
        if int(self.task_tree.cget("height")) != height:
            self.task_tree.configure(height=height)
        self._sync_task_selection()
        self._refresh()

    def _sync_task_selection(self):
        selected = self.selected_task_id()
        current = tuple(self.task_tree.selection())
        if current == ((selected,) if selected is not None else ()):
            return
        if selected is not None:
            self.task_tree.selection_set(selected)
            self.task_tree.see(selected)
        else:
            self.task_tree.selection_remove(self.task_tree.selection())

    def _select_task(self, _event=None):
        selected = self.task_tree.selection()
        task_id = selected[0] if selected else None
        if task_id == self.selected_task_id():
            return
        self.task_states.select(task_id)
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

    def request_admin(self, task_id: str, callback: Callable[[dict[str, str] | None], None],
                      *, rejection: str | None = None) -> None:
        """Collect credentials without blocking polling or other task interactions."""
        from scripts.launcher.installation_probe import ADMIN_INPUT_ERRORS
        if task_id in self._admin_dialogs:
            pending = self._admin_dialogs[task_id]
            if isinstance(rejection, str) and rejection in ADMIN_INPUT_ERRORS:
                pending['callback'] = callback
                pending['submit'].state(['!disabled'])
                for field in pending['fields'].values():
                    field.state(['!disabled'])
                pending['show_error'](*ADMIN_INPUT_ERRORS[rejection])
            pending["dialog"].lift()
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
        ttk.Label(body, text="AW Center’a giriş yapmak için ilk yönetici hesabınızı oluşturun. Kullanıcı adında bir harf ve ardından beş rakam kullanın (ör. U12345). Parolanız 8–128 karakter olmalı. Yalnız rakamlardan oluşan, yaygın veya kullanıcı adınıza benzeyen parolalar kabul edilmez.", wraplength=500).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        variables = {key: tk.StringVar(dialog) for key in ("username", "password", "confirmation")}
        pending = self._admin_dialogs[task_id] = {"dialog": dialog, "variables": variables, "callback": callback}
        fields = {}
        for row, (key, label) in enumerate((("username", "Kullanıcı adı"), ("password", "Parola"), ("confirmation", "Parola tekrarı")), start=1):
            ttk.Label(body, text=label).grid(row=row*2, column=0, sticky="w", padx=(0, 12), pady=6)
            entry = ttk.Entry(body, textvariable=variables[key], width=36, show="*" if key != "username" else "")
            entry.grid(row=row*2, column=1, sticky="ew", pady=6)
            fields[key] = entry
        error_var = tk.StringVar(dialog)
        error_label = ttk.Label(body, textvariable=error_var, wraplength=420)

        def show_error(field, message):
            error_var.set(message)
            error_label.grid(row=fields[field].grid_info()['row'] + 1, column=1, sticky='w')
            fields[field].focus_set()

        def submit():
            if submit_button.instate(['disabled']):
                return
            try:
                result = validate_admin(*(variables[key].get() for key in ("username", "password", "confirmation")))
            except FormError as error:
                show_error(error.field, str(error))
                return
            variables['password'].set('')
            variables['confirmation'].set('')
            for entry in fields.values():
                entry.state(['disabled'])
            submit_button.state(['disabled'])
            error_var.set('Hesap oluşturuluyor…')
            error_label.grid(row=7, column=1, sticky='w')
            try:
                pending['callback'](result)
            except Exception:
                self._finish_admin(task_id, None, notify=False)
                self.handle_event({'task_id': task_id, 'type': 'error', 'code': 'admin_reply_failed',
                                   'message': 'Yönetici bilgileri iletilemedi.'})

        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="İptal", command=lambda: self._finish_admin(task_id, None)).grid(row=0, column=0, padx=(0, 8))
        submit_button = ttk.Button(buttons, text="Yönetici oluştur", command=submit)
        submit_button.grid(row=0, column=1)
        pending.update(fields=fields, submit=submit_button, show_error=show_error)
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
