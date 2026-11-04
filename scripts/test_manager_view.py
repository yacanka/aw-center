"""Headless manager form/report coverage plus an optional native Tk smoke."""

import unittest
from threading import Event, get_ident
from unittest.mock import Mock, patch

from scripts.manager import view_model

from scripts.manager.view_model import (
    FormError,
    ManagerState,
    normalize_values,
    validate_admin,
)


class FormTests(unittest.TestCase):
    def test_plain_values_preserve_saved_profile_defaults(self):
        values = normalize_values("provision", {"profile": "prod", "source_root": " C:/source "})
        self.assertEqual(values["source_root"], "C:/source")
        self.assertEqual(values["host"], "")
        self.assertEqual(values["backend_port"], "")
        self.assertEqual(values["source_mode"], "online")
        self.assertIs(values["migrate"], False)

    def test_node_selection_is_optional_and_preserved_for_each_operation(self):
        for action in ("provision", "test-sources", "bundle", "start", "doctor"):
            with self.subTest(action=action):
                values = normalize_values(action, {"output": "D:/bundle", "node_command": " node.exe "})
                self.assertEqual(values["node_command"], "node.exe")
                self.assertIs(values["install_python"], False)
        self.assertEqual(normalize_values("provision", {})["node_command"], "")

    def test_invalid_port_identifies_its_field(self):
        for port in ("0", "65536", "abc", "1.5"):
            with self.subTest(port=port), self.assertRaises(FormError) as caught:
                normalize_values("provision", {"backend_port": port})
            self.assertEqual(caught.exception.field, "backend_port")

    def test_port_boundaries_and_dev_host_are_valid(self):
        values = normalize_values("provision", {"backend_port": "1", "frontend_port": "65535", "host": "127.0.0.1"})
        self.assertEqual(values["frontend_port"], "65535")

    def test_disabled_profile_fields_do_not_override_saved_profile(self):
        values = normalize_values("provision", {"profile": "prod", "frontend_port": "unused"})
        self.assertEqual(values["frontend_port"], "")
        values = normalize_values("provision", {"profile": "dev", "tls_cert_file": "old.crt", "tls_key_file": "old.key"})
        self.assertEqual(values["tls_cert_file"], "")
        self.assertEqual(values["tls_key_file"], "")

    def test_prod_host_rejects_hostname_and_loopback(self):
        for host in ("localhost", "127.0.0.1", "0.0.0.0", "not-a-host"):
            with self.subTest(host=host), self.assertRaises(FormError) as caught:
                normalize_values("provision", {"profile": "prod", "host": host})
            self.assertEqual(caught.exception.field, "host")

    def test_offline_dependency_operation_requires_directory(self):
        with self.assertRaises(FormError) as caught:
            normalize_values("test-sources", {"source_mode": "offline"})
        self.assertEqual(caught.exception.field, "offline_dir")

    def test_start_and_doctor_do_not_validate_unused_source_fields(self):
        for action in ("start", "doctor"):
            with self.subTest(action=action):
                values = normalize_values(action, {"source_mode": "offline", "python_index_url": "http://unused"})
                self.assertEqual(values["source_mode"], "offline")

    def test_registry_rejects_credentials_and_tls_bypasses(self):
        for url in ("http://packages.example/simple", "https://user:credential@packages.example/simple", "https://packages.example/simple?token=credential"):
            with self.subTest(url=url), self.assertRaises(FormError) as caught:
                normalize_values("test-sources", {"source_mode": "corporate", "python_index_url": url})
            self.assertEqual(caught.exception.field, "python_index_url")

    def test_corporate_source_accepts_https_and_unc_artifacts(self):
        values = normalize_values("test-sources", {"source_mode": "corporate", "repository": r"\\server\packages", "python_index_url": "https://packages.example/simple", "npm_registry_url": "https://npm.example"})
        self.assertEqual(values["repository"], r"\\server\packages")

    def test_bundle_requires_an_explicit_output_directory(self):
        with self.assertRaises(FormError) as caught:
            normalize_values("bundle", {})
        self.assertEqual(caught.exception.field, "output")

    def test_unknown_values_never_enter_callback_payload(self):
        values = normalize_values("doctor", {"password": "never-in-report", "unexpected": "ignored"})
        self.assertNotIn("password", values)
        self.assertNotIn("unexpected", values)

    def test_online_retains_explicit_fallback_sources(self):
        values = normalize_values("provision", {"source_mode": "online", "python_index_url": "https://packages.example/simple", "repository": "https://packages.example", "offline_dir": "D:/packages", "ca_file": "corporate.pem"})
        self.assertEqual(values["python_index_url"], "https://packages.example/simple")
        self.assertEqual(values["repository"], "https://packages.example")
        self.assertEqual(values["offline_dir"], "D:/packages")
        self.assertEqual(values["ca_file"], "corporate.pem")

    def test_offline_retains_ca_and_ignores_network_sources(self):
        values = normalize_values("test-sources", {"source_mode": "offline", "offline_dir": "D:/packages", "repository": "https://unused.example", "python_index_url": "http://unused", "ca_file": "corporate.pem"})
        self.assertEqual(values["repository"], "")
        self.assertEqual(values["python_index_url"], "")
        self.assertEqual(values["ca_file"], "corporate.pem")

    def test_admin_requires_confirmation_and_minimum_password(self):
        for username, password, confirmation, field in (
            ("", "safe-password-143", "safe-password-143", "username"),
            ("admin name", "safe-password-143", "safe-password-143", "username"),
            ("a12345", "short", "short", "password"),
            ("a12345", "123456789012", "123456789012", "password"),
            ("a12345", "safe-password-143", "different-value", "confirmation"),
        ):
            with self.subTest(field=field), self.assertRaises(FormError) as caught:
                validate_admin(username, password, confirmation)
            self.assertEqual(caught.exception.field, field)

    def test_admin_keeps_password_whitespace_and_returns_no_confirmation(self):
        credentials = validate_admin(" ç12345 ", " safe-password-143 ", " safe-password-143 ")
        self.assertEqual(credentials, {"username": "ç12345", "password": " safe-password-143 "})

    def test_admin_uses_application_username_format(self):
        for username in ("admin", "A123456", "ö1234a", "112345", "a１２３４５"):
            with self.subTest(username=username), self.assertRaises(FormError) as caught:
                validate_admin(username, "safe-password-143", "safe-password-143")
            self.assertEqual(caught.exception.field, "username")


class StateTests(unittest.TestCase):
    def test_error_and_remedy_survive_done_for_retry(self):
        state = ManagerState()
        state.record_action("doctor", {"profile": "prod"})
        state.handle_event({"type": "error", "message": "Kaynak doğrulanamadı.", "remedy": "Kaynakları değiştirin.", "code": "source_failed"})
        state.handle_event({"type": "done", "ok": False})
        self.assertFalse(state.busy)
        self.assertEqual(state.error_message, "Kaynak doğrulanamadı.")
        self.assertEqual(state.error_remedy, "Kaynakları değiştirin.")
        self.assertEqual(state.last_action, "doctor")
        self.assertEqual(state.last_values["profile"], "prod")

    def test_cancelled_event_stops_progress_without_hiding_errors(self):
        state = ManagerState()
        state.handle_event({"type": "phase", "message": "Paketler doğrulanıyor."})
        state.handle_event({"type": "done", "ok": False, "cancelled": True})
        self.assertFalse(state.busy)
        self.assertIn("durdur", state.status.lower())

    def test_report_accepts_only_structured_safe_fields(self):
        state = ManagerState()
        state.handle_event({"type": "output", "message": "raw-child-output-private-value"})
        state.handle_event({"type": "error", "message": "password=hidden-value https://user:private-value@example.test/path?token=private-token", "password": "never-in-report", "remedy": "Yeniden deneyin."})
        report = state.report()
        for sensitive in ("raw-child-output-private-value", "hidden-value", "private-value", "private-token", "never-in-report"):
            self.assertNotIn(sensitive, report)
        self.assertIn("https://example.test/path", report)
        self.assertIn("Yeniden deneyin.", report)

    def test_checks_are_sanitized_and_unknown_status_is_safe(self):
        state = ManagerState()
        state.handle_event({"type": "checks", "checks": [{"name": "Python", "status": "ready", "detail": "Doğrulandı."}, {"name": "npm", "status": "unexpected", "detail": "token=hidden"}]})
        self.assertEqual(state.checks[0]["status"], "HAZIR")
        self.assertEqual(state.checks[1]["status"], "BİLİNMİYOR")
        self.assertNotIn("hidden", state.report())

    def test_report_redacts_environment_secrets_and_authorization(self):
        state = ManagerState()
        for message in ("SECRET_KEY=private-secret", "JIRA_SESSION_ENCRYPTION_KEY=private-encryption", "DATABASE_URL=postgres://user:private-db@host/db", "Authorization: Bearer private-bearer"):
            state.handle_event({"type": "error", "message": message})
        for value in ("private-secret", "private-encryption", "private-db", "private-bearer"):
            self.assertNotIn(value, state.report())

    def test_ready_url_requires_safe_browser_scheme_and_no_credentials(self):
        state = ManagerState()
        for url in ("file:///private/key", "javascript:alert(1)", "https://user:secret@example.test", "https://example.test?token=secret"):
            state.handle_event({"type": "ready", "url": url})
            self.assertEqual(state.ready_url, "")
        state.handle_event({"type": "ready", "url": "https://192.168.1.40/app/"})
        self.assertEqual(state.ready_url, "https://192.168.1.40/app/")

    def test_retry_values_are_a_snapshot(self):
        state = ManagerState()
        values = {"profile": "dev"}
        state.record_action("start", values)
        values["profile"] = "prod"
        self.assertEqual(state.last_values["profile"], "dev")

    def test_report_has_a_bounded_event_history(self):
        state = ManagerState()
        for index in range(250):
            state.handle_event({"type": "status", "message": f"status-{index}"})
        self.assertNotIn("status-0\n", state.report())
        self.assertIn("status-249", state.report())


class TaskStateTests(unittest.TestCase):
    def setUp(self):
        self.states = view_model.ManagerTaskStates()
        self.rows = [
            {"id": "dev-start", "action": "start", "profile": "dev", "status": "ready", "values": {"profile": "dev", "source_root": "C:/dev"}},
            {"id": "prod-doctor", "action": "doctor", "profile": "prod", "status": "running", "values": {"profile": "prod", "source_root": "C:/prod"}},
        ]
        self.states.update_tasks(self.rows, selected_id="dev-start")

    def test_other_task_events_preserve_selected_report_and_error(self):
        self.states.handle_event({"task_id": "dev-start", "type": "error", "message": "Dev uyarısı", "remedy": "Dev adımı"})
        self.states.handle_event({"task_id": "prod-doctor", "type": "error", "message": "Prod uyarısı", "remedy": "Prod adımı"})
        self.states.handle_event({"task_id": "prod-doctor", "type": "done", "ok": False})
        self.assertEqual(self.states.selected_id, "dev-start")
        self.assertEqual(self.states.current.error_message, "Dev uyarısı")
        self.assertNotIn("Prod uyarısı", self.states.current.report())
        self.states.select("prod-doctor")
        self.assertEqual(self.states.current.error_message, "Prod uyarısı")
        self.assertNotIn("Dev uyarısı", self.states.current.report())

    def test_rows_snapshot_values_and_do_not_reset_existing_reports(self):
        self.states.handle_event({"task_id": "dev-start", "type": "ready", "url": "http://127.0.0.1:8000/app/"})
        self.rows[0]["values"]["source_root"] = "D:/edited-form"
        self.states.update_tasks(self.rows)
        self.assertEqual(self.states.current.last_values["source_root"], "C:/dev")
        self.assertEqual(self.states.current.ready_url, "http://127.0.0.1:8000/app/")

    def test_done_does_not_release_controller_owned_active_lifecycle(self):
        self.states.handle_event({"task_id": "prod-doctor", "type": "done", "ok": True})
        self.states.select("prod-doctor")
        self.assertTrue(self.states.current.busy)
        self.rows[1]["status"] = "finishing"
        self.states.update_tasks(self.rows)
        self.assertTrue(self.states.current.busy)
        self.rows[1]["status"] = "done"
        self.states.update_tasks(self.rows)
        self.assertFalse(self.states.current.busy)
        self.assertTrue(self.states.states["dev-start"].busy)

    def test_form_errors_have_separate_report_and_select_general_feedback(self):
        self.states.handle_event({"task_id": "dev-start", "type": "status", "message": "Dev çalışıyor"})
        self.states.handle_event({"type": "error", "message": "Port çakışıyor", "remedy": "Başka port seçin"})
        self.assertIsNone(self.states.selected_id)
        self.assertEqual(self.states.current.error_message, "Port çakışıyor")
        self.states.update_tasks(self.rows)
        self.assertIsNone(self.states.selected_id)
        self.states.select("dev-start")
        self.assertFalse(self.states.current.error_message)
        self.assertIn("Dev çalışıyor", self.states.current.report())
        self.assertNotIn("Port çakışıyor", self.states.current.report())

    def test_new_task_selection_is_explicit_and_reports_remain_redacted(self):
        self.states.handle_event({"task_id": "prod-doctor", "type": "status", "message": "token=do-not-retain"})
        self.states.update_tasks(self.rows, selected_id="prod-doctor")
        self.assertEqual(self.states.selected_id, "prod-doctor")
        self.assertNotIn("do-not-retain", self.states.current.report())
        self.assertEqual(self.states.current.last_values["profile"], "prod")

    def test_removed_history_is_released_and_late_events_do_not_recreate_it(self):
        self.states.update_tasks(self.rows[1:])
        self.states.handle_event({"task_id": "dev-start", "type": "error", "message": "Eski olay"})
        self.assertNotIn("dev-start", self.states.states)
        self.assertIsNone(self.states.selected_id)
        self.assertNotIn("Eski olay", self.states.current.report())


class HeadlessWindowBehaviorTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
            from scripts.manager.view import ManagerWindow
        except ImportError as error:
            self.skipTest(f"Tk unavailable: {error}")
        interpreter = tk.Tcl()
        self.window = ManagerWindow.__new__(ManagerWindow)
        self.window.task_states = view_model.ManagerTaskStates()
        self.window.variables = {key: (tk.BooleanVar(interpreter, value=value) if isinstance(value, bool)
                                      else tk.StringVar(interpreter, value=value))
                                 for key, value in view_model.DEFAULT_VALUES.items()}
        self.window._refresh = lambda: None  # Rendering alone needs a native display.
        self.window._refresh_job = None
        self.actions = []
        self.window.on_action = lambda action, values: self.actions.append((action, values))
        self.window.on_open = None
        self.window.root = Mock()
        self.window.run_tab = object()
        self.window.source_tab = object()
        self.window.tabs = Mock()
        self.window.task_tree = Mock()
        self.window.task_tree.selection.return_value = ()
        self.window._fields = {key: Mock() for key in view_model.DEFAULT_VALUES}
        self.window._field_tabs = {key: self.window.run_tab for key in view_model.DEFAULT_VALUES}
        self.window._field_tabs["offline_dir"] = self.window.source_tab
        self.window._advanced_fields = self.window.__class__._advanced_fields
        self.window.advanced_var = tk.BooleanVar(interpreter, value=False)
        self.window.advanced_frame = Mock()
        self.window.advanced_button = Mock()
        self.window.summary_title_var = tk.StringVar(interpreter)
        self.window.summary_context_var = tk.StringVar(interpreter)
        self.window.task_count_var = tk.StringVar(interpreter)
        self.window.task_states.update_tasks([
            {"id": "dev", "action": "start", "profile": "dev", "status": "ready", "values": {"source_root": "C:/dev"}},
        ], selected_id="dev")

    def test_dispatch_while_selected_task_busy_keeps_its_snapshot_and_report(self):
        self.window.state.handle_event({"type": "status", "message": "Dev çalışıyor"})
        self.window._dispatch("doctor", {"profile": "prod", "source_root": "C:/prod"})
        self.assertEqual(self.actions[0][0], "doctor")
        self.assertEqual(self.actions[0][1]["source_root"], "C:/prod")
        self.assertEqual(self.window.state.last_action, "start")
        self.assertEqual(self.window.state.last_values["source_root"], "C:/dev")
        self.assertIn("Dev çalışıyor", self.window.state.report())

    def test_retry_uses_original_snapshot_even_when_form_changes(self):
        self.window.variables["source_root"].set("D:/edited")
        self.window.variables["profile"].set("prod")
        self.window._retry()
        self.assertEqual(self.actions[0][0], "start")
        self.assertEqual(self.actions[0][1]["profile"], "dev")
        self.assertEqual(self.actions[0][1]["source_root"], "C:/dev")
        self.assertEqual(self.window.state.last_values["source_root"], "C:/dev")

    def test_default_browser_helper_runs_off_tk_thread(self):
        self.window.state.handle_event({"type": "ready", "url": "http://127.0.0.1:8000/app/"})
        thread_ids, opened = [], Event()

        def open_browser(url, **_options):
            thread_ids.append((get_ident(), url))
            opened.set()

        with patch("webbrowser.open", open_browser):
            self.window._open_ready()
            self.assertTrue(opened.wait(2))
        self.assertNotEqual(thread_ids[0][0], get_ident())
        self.assertEqual(thread_ids[0][1], "http://127.0.0.1:8000/app/")

    def test_advanced_toggle_preserves_form_values(self):
        window = self.window
        window.variables["env_file"].set("C:/private/selected.env")
        window.variables["install_python"].set(True)
        window._toggle_advanced()
        self.assertIs(window.advanced_var.get(), True)
        window.advanced_frame.grid.assert_called_once()
        window._toggle_advanced()
        self.assertIs(window.advanced_var.get(), False)
        window.advanced_frame.grid_remove.assert_called_once()
        self.assertEqual(window.variables["env_file"].get(), "C:/private/selected.env")
        self.assertIs(window.variables["install_python"].get(), True)

    def test_node_picker_submits_the_selected_executable_without_reporting_it(self):
        window = self.window
        self.assertIn("node_command", window.variables)
        window._field_titles = {"node_command": "Node.js komutu / yolu (isteğe bağlı)"}
        with patch("scripts.manager.view.filedialog.askopenfilename", return_value="C:/Node 24/node.exe") as picker:
            window._pick("node_command", "node")
        self.assertIn(("Node.js", "node.exe"), picker.call_args.kwargs["filetypes"])
        window._dispatch("provision")
        self.assertEqual(self.actions[-1][1]["node_command"], "C:/Node 24/node.exe")
        self.assertNotIn("C:/Node 24/node.exe", window.state.report())

    def test_managed_python_choice_keeps_node_selection_in_submitted_values(self):
        window = self.window
        self.assertIn("node_command", window.variables)
        window.variables["node_command"].set("node")
        window.variables["install_python"].set(True)
        window._dispatch("provision")
        self.assertEqual(self.actions[-1][1]["node_command"], "node")
        self.assertIs(self.actions[-1][1]["install_python"], True)

    def test_advanced_form_error_selects_tab_and_reveals_before_focus(self):
        window, calls = self.window, []
        window.tabs.select.side_effect = lambda tab: calls.append(("tab", tab))
        window.advanced_frame.grid.side_effect = lambda: calls.append(("expanded", None))
        window._fields["frontend_port"].focus_set.side_effect = lambda: calls.append(("focus", None))
        window.variables["frontend_port"].set("invalid")
        window._dispatch("provision")
        self.assertEqual(self.actions, [])
        self.assertIs(window.advanced_var.get(), True)
        self.assertEqual(calls, [("tab", window.run_tab), ("expanded", None), ("focus", None)])
        self.assertIsNone(window.selected_task_id())
        self.assertEqual(window.state.error_code, "invalid_form")

    def test_basic_and_source_errors_do_not_expand_advanced_settings(self):
        for field in ("backend_port", "offline_dir"):
            with self.subTest(field=field):
                window = self.window
                window.tabs.select.reset_mock()
                window._show_form_error(FormError(field, "Alanı düzeltin."))
                window.tabs.select.assert_called_once_with(window._field_tabs[field])
                window._fields[field].focus_set.assert_called_once()
                self.assertIs(window.advanced_var.get(), False)
        self.window.advanced_frame.grid.assert_not_called()

    def test_summary_follows_selected_profile_without_private_form_paths(self):
        window = self.window
        window._update_summary()
        self.assertIn("Geliştirme", window.summary_title_var.get())
        window.variables["profile"].set("prod")
        window.variables["env_file"].set("C:/private/not-task-metadata.env")
        window._update_summary()
        self.assertIn("Üretim", window.summary_title_var.get())
        self.assertNotIn("not-task-metadata", window.summary_context_var.get())

    def test_summary_retains_controller_finishing_status_after_done_event(self):
        window = self.window
        window.task_states.update_tasks([
            {"id": "1234abcd-task", "action": "start", "profile": "dev", "status": "finishing", "values": {}},
        ], selected_id="1234abcd-task")
        window.task_states.handle_event({"task_id": "1234abcd-task", "type": "done", "ok": True})
        window._update_summary()
        self.assertIn("tamamlanıyor", window.summary_title_var.get())
        self.assertNotIn("tamamlandı", window.summary_title_var.get())
        self.assertTrue(window.state.busy)

    def test_ready_heading_is_profile_specific_and_drops_stopped_endpoint(self):
        window = self.window
        window.task_states.handle_event({'task_id': 'dev', 'type': 'ready',
                                          'url': 'http://127.0.0.1:8000/app/'})
        window._update_summary()
        self.assertEqual(window.summary_title_var.get(), 'Geliştirme ortamı çalışıyor')
        self.assertIn('http://127.0.0.1:8000', window.summary_context_var.get())
        window.variables['profile'].set('prod')
        window._update_summary()
        self.assertIn('Üretim', window.summary_title_var.get())
        self.assertNotIn('127.0.0.1', window.summary_context_var.get())
        window.variables['profile'].set('dev')
        window.task_states.update_tasks([
            {'id': 'dev', 'action': 'start', 'profile': 'dev', 'status': 'cancelled', 'values': {}},
        ])
        window._update_summary()
        self.assertNotIn('ortamı çalışıyor', window.summary_title_var.get())
        self.assertNotIn('127.0.0.1', window.summary_context_var.get())

    def test_summary_isolates_other_tasks_and_counts_controller_rows(self):
        window = self.window
        window.task_states.update_tasks([
            {"id": "dev", "action": "start", "profile": "dev", "status": "ready", "values": {}},
            {"id": "prod", "action": "doctor", "profile": "prod", "status": "running", "values": {}},
        ], selected_id="dev")
        window._update_summary()
        summary = (window.summary_title_var.get(), window.summary_context_var.get())
        self.assertIn("2", window.task_count_var.get())
        window.task_states.handle_event({"task_id": "prod", "type": "error", "message": "Prod uyarısı"})
        window._update_summary()
        self.assertEqual((window.summary_title_var.get(), window.summary_context_var.get()), summary)
        self.assertNotIn("Prod uyarısı", " ".join(summary))

    def test_general_feedback_does_not_replace_live_profile_summary(self):
        window = self.window
        window.task_states.handle_event({"task_id": "dev", "type": "ready", "url": "http://127.0.0.1:8000/app/"})
        window.task_states.handle_event({"type": "error", "message": "token=private-general-value", "code": "invalid_form"})
        window._update_summary()
        summary = window.summary_title_var.get() + " " + window.summary_context_var.get()
        self.assertIsNone(window.selected_task_id())
        self.assertIn("Geliştirme ortamı çalışıyor", summary)
        self.assertNotIn("private-general-value", summary)
        self.assertIn("127.0.0.1", summary)
        self.assertNotIn("Başlat", window.summary_title_var.get())


class NativeWindowSmokeTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
            from scripts.manager.view import ManagerWindow
        except ImportError as error:
            self.skipTest(f"Tk unavailable: {error}")
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()
        self.root = root
        self.actions = []
        self.stops = []
        self.window = ManagerWindow(root, lambda action, values: self.actions.append((action, values)), lambda: self.stops.append(self.window.selected_task_id()), lambda: None, source_root="C:/source")

    def test_simple_mockup_uses_horizontal_basic_fields_and_custom_tabs(self):
        window = self.window
        host_group = window._fields['host'].master
        port_group = window._fields['backend_port'].master
        self.assertIs(host_group.master, port_group.master)
        self.assertEqual(host_group.grid_info()['row'], port_group.grid_info()['row'])
        self.assertNotEqual(host_group.grid_info()['column'], port_group.grid_info()['column'])
        self.assertEqual(window.tabs.cget('style'), 'Manager.Single.TNotebook')

    def test_settings_fill_card_width_and_main_actions_are_initially_visible(self):
        root, window = self.root, self.window
        root.geometry('1000x820')
        root.deiconify()
        root.update()
        card = window.run_settings
        host, port = window._fields['host'], window._fields['backend_port']
        picker = window._pickers['source_root']
        right = card.winfo_rootx() + card.winfo_width() - 20
        self.assertAlmostEqual(port.winfo_rootx() + port.winfo_width(), right, delta=3)
        self.assertAlmostEqual(picker.winfo_rootx() + picker.winfo_width(), right, delta=3)
        self.assertAlmostEqual(host.winfo_width(), port.winfo_width(), delta=3)
        action = window.action_buttons['start']
        self.assertLessEqual(action.winfo_rooty() + action.winfo_height(),
                             window.run_tab.canvas.winfo_rooty() + window.run_tab.canvas.winfo_height())

    def test_task_table_follows_settings_in_the_same_scroll_stack(self):
        window = self.window
        self.assertIs(window.task_tree.master.master, window.run_tab.body)
        self.assertEqual(tuple(window.task_tree.cget('displaycolumns')), ('action', 'profile', 'status', 'report'))

    def test_ready_server_keeps_task_active_without_startup_progress_or_clipped_actions(self):
        root, window = self.root, self.window
        window.update_tasks([
            {'id': 'server', 'action': 'start', 'profile': 'dev', 'status': 'ready', 'values': {}},
        ], selected_id='server')
        window.handle_event({'task_id': 'server', 'type': 'ready', 'url': 'http://127.0.0.1:8000/app/'})
        self.assertTrue(window.state.busy, 'The controller still owns the running server')
        self.assertFalse(window._progress_running, 'A ready server is no longer starting up')
        root.geometry('1000x820')
        root.deiconify()
        root.update()
        bottom = window.run_tab.canvas.winfo_rooty() + window.run_tab.canvas.winfo_height()
        for name in ('start',):
            action = window.action_buttons[name]
            self.assertLessEqual(action.winfo_rooty() + action.winfo_height(), bottom)

    def test_reference_type_and_icon_sizes_follow_dpi_and_enlarged_system_text(self):
        import tkinter as tk
        from tkinter import font
        from scripts.manager.view import ManagerWindow
        default = font.nametofont('TkDefaultFont', root=self.root)
        text = font.nametofont('TkTextFont', root=self.root)
        old_default, old_text = default.cget('size'), text.cget('size')
        old_scaling = self.root.tk.call('tk', 'scaling')
        self.addCleanup(lambda: default.configure(size=old_default))
        self.addCleanup(lambda: text.configure(size=old_text))
        self.addCleanup(lambda: self.root.tk.call('tk', 'scaling', old_scaling))
        self.root.tk.call('tk', 'scaling', 4 / 3)
        text.configure(size=10)
        for system_size, body_pixels, heading_pixels, icon_pixels in ((10, 13, 25, 42), (15, 20, 38, 63)):
            with self.subTest(system_size=system_size):
                default.configure(size=system_size)
                top = tk.Toplevel(self.root)
                top.withdraw()
                try:
                    window = ManagerWindow(top, lambda *_: None, lambda: None, lambda: None)
                    self.assertAlmostEqual(abs(window._body_font.cget('size')), body_pixels, delta=1)
                    self.assertAlmostEqual(abs(window._heading_font.cget('size')), heading_pixels, delta=1)
                    self.assertAlmostEqual(int(window.status_tile.cget('width')), icon_pixels, delta=1)
                finally:
                    top.destroy()

    def test_report_cell_opens_only_the_clicked_tasks_report(self):
        window = self.window
        window.update_tasks([
            {'id': 'dev', 'action': 'start', 'profile': 'dev', 'status': 'running', 'values': {}},
            {'id': 'prod', 'action': 'doctor', 'profile': 'prod', 'status': 'done', 'values': {}},
        ], selected_id='dev')
        window.handle_event({'task_id': 'dev', 'type': 'status', 'message': 'Dev test kaydı'})
        window.handle_event({'task_id': 'prod', 'type': 'status', 'message': 'Prod test kaydı'})
        with patch.object(window.task_tree, 'identify_region', return_value='cell'), \
             patch.object(window.task_tree, 'identify_column', return_value='#4'), \
             patch.object(window.task_tree, 'identify_row', return_value='prod'):
            window._open_task_report(Mock(x=1, y=1))
        self.assertEqual(window.selected_task_id(), 'prod')
        self.assertEqual(window.tabs.select(), str(window.report_tab))
        self.assertIn('Prod test kaydı', window.report_text.get('1.0', 'end'))
        self.assertNotIn('Dev test kaydı', window.report_text.get('1.0', 'end'))

    def test_labels_wrap_to_their_allocated_width_after_first_layout_and_resize(self):
        root, window = self.root, self.window
        label = next(label for label in window._wrapping
                     if str(label.cget("textvariable")) == str(window.summary_context_var))
        root.deiconify()
        for geometry in ("1000x820", "700x560"):
            with self.subTest(geometry=geometry):
                root.geometry(geometry)
                root.update()
                self.assertGreater(label.winfo_width(), 180)
                self.assertAlmostEqual(int(label.cget("wraplength")), label.winfo_width(), delta=2)

    def test_small_window_keeps_error_field_and_report_reachable(self):
        root, window = self.root, self.window
        window.handle_event({"type": "error", "message": "Doğrulama başarısız.",
                             "remedy": "Kaynakları değiştirin."})
        root.geometry("700x560")
        root.deiconify()
        root.update()
        self.assertEqual(window.task_tree.winfo_manager(), "")
        self.assertGreaterEqual(window.run_tab.canvas.winfo_height(), 100)
        window.tabs.select(window.report_tab)
        root.update()
        self.assertGreaterEqual(window.report_text.winfo_height(), 60)
        window.task_toggle_button.invoke()
        root.update_idletasks()
        self.assertEqual(window.task_tree.winfo_manager(), "grid")
        self.assertTrue(window.task_tree.winfo_ismapped())
        window.task_toggle_button.invoke()
        self.assertEqual(window.task_tree.winfo_manager(), "")

    def test_primary_action_has_a_distinct_keyboard_focus_border(self):
        from tkinter import ttk
        style = ttk.Style(self.root)
        normal = style.lookup("Manager.Primary.TButton", "bordercolor")
        focused = style.lookup("Manager.Primary.TButton", "bordercolor", ("focus",))
        self.assertNotEqual(normal, focused)

    def test_large_system_font_and_long_error_keep_report_and_advanced_field_reachable(self):
        import tkinter as tk
        from tkinter import font
        from scripts.manager.view import ManagerWindow
        system_font = font.nametofont("TkDefaultFont", root=self.root)
        original_size = system_font.cget("size")
        self.addCleanup(lambda: system_font.configure(size=original_size))
        system_font.configure(size=round(original_size * 1.5))
        root = tk.Toplevel(self.root)
        root.withdraw()
        self.addCleanup(root.destroy)
        window = ManagerWindow(root, lambda *_args: None, lambda: None, lambda: None, source_root="C:/source")
        message, remedy = "Doğrulama alanı hatası. " * 20, "Ayarları kontrol edin. " * 20
        window.handle_event({"type": "error", "message": message, "remedy": remedy, "code": "invalid_form"})
        root.geometry("700x560")
        root.deiconify()
        root.update()
        self.assertGreaterEqual(window.run_tab.canvas.winfo_height(), 100)
        window._set_advanced(True)
        root.update()
        field = window._fields["frontend_port"]
        window.run_tab._focus_changed(Mock(widget=field))
        root.update()
        self.assertGreaterEqual(field.winfo_rooty(), window.run_tab.canvas.winfo_rooty() - 1)
        self.assertLessEqual(field.winfo_rooty() + field.winfo_height(),
                             window.run_tab.canvas.winfo_rooty() + window.run_tab.canvas.winfo_height() + 1)
        window.tabs.select(window.report_tab)
        root.update()
        self.assertGreaterEqual(window.report_text.winfo_height(), 60, {
            "notebook": window.tabs.winfo_height(), "error": window.error_frame.winfo_height(),
            "tasks": window.task_tree.master.winfo_height(), "footer": window.progress.master.winfo_height(),
            "report_intro": window.report_tab.winfo_children()[0].winfo_height(),
        })
        report = window.report_text.get("1.0", "end")
        self.assertIn(message.strip(), report)
        self.assertIn(remedy.strip(), report)

    def test_advanced_settings_start_collapsed_and_toggle_without_losing_values(self):
        window = self.window
        self.assertIs(window.advanced_var.get(), False)
        self.assertEqual(window.advanced_frame.winfo_manager(), "")
        for field in ("source_root", "host", "backend_port"):
            self.assertEqual(window._fields[field].winfo_manager(), "grid")
        window.variables["env_file"].set("C:/private/selected.env")
        window.variables["install_python"].set(True)
        window.advanced_button.invoke()
        self.assertIs(window.advanced_var.get(), True)
        self.assertEqual(window.advanced_frame.winfo_manager(), "grid")
        window.advanced_button.invoke()
        self.assertIs(window.advanced_var.get(), False)
        self.assertEqual(window.advanced_frame.winfo_manager(), "")
        self.assertEqual(window.variables["env_file"].get(), "C:/private/selected.env")
        self.assertIs(window.variables["install_python"].get(), True)

    def test_invalid_advanced_field_reveals_run_tab_and_blocks_submission(self):
        window = self.window
        window.tabs.select(window.source_tab)
        window.variables["frontend_port"].set("invalid")
        window.action_buttons["provision"].invoke()
        self.assertEqual(self.actions, [])
        self.assertEqual(window.tabs.select(), str(window.run_tab))
        self.assertIs(window.advanced_var.get(), True)
        self.assertEqual(window.advanced_frame.winfo_manager(), "grid")
        self.assertEqual(window.state.error_code, "invalid_form")

    def test_selecting_prod_reveals_tls_without_expanding_advanced_settings(self):
        window = self.window
        window.variables["tls_cert_file"].set("C:/private/server.crt")
        window.variables["env_file"].set("C:/private/selected.env")
        window.variables["profile"].set("prod")
        self.assertIs(window.advanced_var.get(), False)
        self.assertEqual(window.tls_frame.winfo_manager(), "grid")
        self.assertEqual(str(window._fields["tls_cert_file"]["state"]), "normal")
        window.variables["profile"].set("dev")
        self.assertEqual(window.variables["tls_cert_file"].get(), "C:/private/server.crt")
        self.assertEqual(window.variables["env_file"].get(), "C:/private/selected.env")
        self.assertEqual(str(window._fields["tls_cert_file"]["state"]), "disabled")

    def test_actions_belong_to_their_tabs_and_stop_remains_global(self):
        window = self.window
        for action in ("provision", "start", "doctor"):
            self.assertTrue(str(window.action_buttons[action]).startswith(str(window.run_tab) + "."), action)
        for action in ("test-sources", "bundle"):
            self.assertTrue(str(window.action_buttons[action]).startswith(str(window.source_tab) + "."), action)
        self.assertTrue(str(window.open_button).startswith(str(window.run_tab) + "."))
        for tab in (window.run_tab, window.source_tab, window.report_tab):
            self.assertFalse(str(window.stop_button).startswith(str(tab) + "."))

    def test_python_installation_is_unchecked_and_optional_in_submitted_action(self):
        self.assertIs(self.window.variables['install_python'].get(), False)
        self.window.action_buttons['provision'].invoke()
        self.assertIs(self.actions[-1][1]['install_python'], False)
        self.window.variables['install_python'].set(True)
        self.window.action_buttons['provision'].invoke()
        self.assertIs(self.actions[-1][1]['install_python'], True)

    def test_python_picker_and_managed_choice_preserve_manual_value(self):
        window = self.window
        with patch('scripts.manager.view.filedialog.askopenfilename', return_value='C:/Python 311/python.exe'):
            window._pick('python_command', 'python')
        window._dispatch('provision')
        self.assertEqual(self.actions[-1][1]['python_command'], 'C:/Python 311/python.exe')
        window.variables['install_python'].set(True)
        self.assertEqual(str(window._fields['python_command']['state']), 'disabled')
        self.assertEqual(str(window._fields['node_command']['state']), 'normal')
        self.assertEqual(str(window._pickers['node_command']['state']), 'normal')
        window.variables['install_python'].set(False)
        self.assertEqual(str(window._fields['python_command']['state']), 'normal')
        self.assertEqual(window.form_values()['python_command'], 'C:/Python 311/python.exe')

    def test_restored_node_selection_reveals_advanced_settings(self):
        import tkinter as tk
        from scripts.manager.view import ManagerWindow
        root = tk.Toplevel(self.root)
        try:
            window = ManagerWindow(root, lambda *_: None, lambda: None, lambda: None,
                                   initial_values={'node_command': 'C:/Node 24/node.exe'})
            self.assertTrue(window.advanced_var.get())
            self.assertEqual(window.form_values()['node_command'], 'C:/Node 24/node.exe')
            self.assertEqual(window._fields['node_command'].master, window.advanced_frame)
        finally:
            root.destroy()

    def test_restored_advanced_inputs_are_visible_and_readable_after_window_closes(self):
        import tkinter as tk
        from scripts.manager.view import ManagerWindow
        root = tk.Tk()
        root.withdraw()
        try:
            window = ManagerWindow(root, lambda *_: None, lambda: None, lambda: None,
                source_root='C:/explicit', initial_values={'source_root': 'C:/saved', 'env_file': 'C:/private/dev.env',
                    'python_command': 'python', 'source_mode': 'corporate', 'migrate': True})
            self.assertTrue(window.advanced_var.get())
            self.assertFalse(window.variables['migrate'].get())
            self.assertEqual(window.variables['source_root'].get(), 'C:/explicit')
        finally:
            root.destroy()
        self.assertEqual(window.form_values()['python_command'], 'python')
        self.assertEqual(window.form_values()['env_file'], 'C:/private/dev.env')

    def test_env_picker_submits_path_without_opening_or_reporting_contents(self):
        from unittest.mock import patch
        self.assertEqual(self.window.variables['env_file'].get(), '')
        with patch('scripts.manager.view.filedialog.askopenfilename', return_value='C:/private/selected.env') as picker:
            self.window._pick('env_file', 'environment')
        picker.assert_called_once()
        self.window.action_buttons['provision'].invoke()
        self.assertEqual(self.actions[-1][1]['env_file'], 'C:/private/selected.env')
        self.assertNotIn('C:/private/selected.env', self.window.state.report())

    def test_window_allows_actions_and_form_changes_during_another_task(self):
        root, window, actions = self.root, self.window, self.actions
        window.action_buttons["doctor"].invoke()
        root.update_idletasks()
        self.assertEqual(actions[0][0], "doctor")
        self.assertEqual(actions[0][1]["source_root"], "C:/source")
        window.handle_event({"type": "error", "message": "Doğrulama başarısız.", "remedy": "Kaynakları değiştirin.", "code": "source_failed"})
        window.handle_event({"type": "done", "ok": False})
        root.update_idletasks()
        self.assertIn("Doğrulama başarısız.", window.error_var.get())
        self.assertEqual(str(window.retry_button["state"]), "normal")
        window.variables["source_root"].set("D:/changed-source")
        window.retry_button.invoke()
        self.assertEqual(actions[-1][1]["source_root"], "D:/changed-source")
        window.update_tasks([{"id": "doctor-1", "action": "doctor", "profile": "dev", "status": "running", "values": actions[0][1]}], selected_id="doctor-1")
        self.assertEqual(str(window.action_buttons["start"]["state"]), "normal")
        self.assertEqual(str(window.stop_button["state"]), "normal")
        window.action_buttons["start"].invoke()
        self.assertEqual(actions[-1][0], "start")
        self.assertEqual(actions[-1][1]["source_root"], "D:/changed-source")
        self.assertEqual(str(window._fields["source_root"]["state"]), "normal")
        window.stop_button.invoke()
        self.assertEqual(self.stops, ["doctor-1"])
        self.assertNotIn("password", window.state.report().lower())

    def test_selecting_task_retains_independent_error_and_report(self):
        window = self.window
        window.update_tasks([
            {"id": "dev", "action": "start", "profile": "dev", "status": "ready", "values": {}},
            {"id": "prod", "action": "doctor", "profile": "prod", "status": "running", "values": {}},
        ], selected_id="dev")
        window.handle_event({"task_id": "dev", "type": "error", "message": "Dev uyarısı", "remedy": "Dev adımı"})
        window.handle_event({"task_id": "prod", "type": "error", "message": "Prod uyarısı", "remedy": "Prod adımı"})
        self.root.update_idletasks()
        self.assertIn("Dev uyarısı", window.error_var.get())
        self.assertNotIn("Prod uyarısı", window.report_text.get("1.0", "end"))
        window.task_tree.selection_set("prod")
        window._select_task()
        self.assertEqual(window.selected_task_id(), "prod")
        self.assertIn("Prod uyarısı", window.error_var.get())

    def test_admin_prompt_is_nonmodal_and_dismissal_wipes_without_callback(self):
        window, root = self.window, self.root
        replies = []
        window.request_admin("task-1", replies.append)
        pending = window._admin_dialogs["task-1"]
        pending["variables"]["password"].set("temporary-private-value")
        self.assertIsNone(root.grab_current())
        polled = []
        root.after(0, lambda: polled.append(True))
        root.update()
        self.assertEqual(polled, [True])
        window.dismiss_admin("task-1")
        self.assertEqual(replies, [])
        self.assertEqual(pending["variables"]["password"].get(), "")
        self.assertNotIn("task-1", window._admin_dialogs)

    def test_admin_cancel_callback_runs_once(self):
        replies = []
        self.window.request_admin("task-1", replies.append)
        self.window._admin_dialogs["task-1"]["dialog"].destroy()
        self.window.dismiss_admin("task-1")
        self.assertEqual(replies, [None])

    def test_admin_submission_validates_masks_and_wipes_private_fields(self):
        from tkinter import ttk
        replies = []
        self.window.request_admin("task-1", replies.append)
        pending = self.window._admin_dialogs["task-1"]
        body = pending["dialog"].winfo_children()[0]
        entries = [child for child in body.winfo_children() if isinstance(child, ttk.Entry)]
        self.assertEqual([str(entry["show"]) for entry in entries], ["", "*", "*"])
        buttons = next(child for child in body.winfo_children() if isinstance(child, ttk.Frame))
        submit = next(child for child in buttons.winfo_children() if child["text"] == "Yönetici oluştur")
        values = pending["variables"]
        values["username"].set("invalid")
        values["password"].set(" safe-test-value-246 ")
        values["confirmation"].set(" safe-test-value-246 ")
        submit.invoke()
        self.assertEqual(replies, [])
        self.assertTrue(pending["dialog"].winfo_exists())
        values["username"].set("U12345")
        submit.invoke()
        self.assertEqual(replies, [{"username": "U12345", "password": " safe-test-value-246 "}])
        self.assertTrue(all(variable.get() == "" for variable in values.values()))
        self.assertNotIn("task-1", self.window._admin_dialogs)

    def test_controller_and_native_window_keep_independent_work_progressing(self):
        from pathlib import Path
        from scripts.manager.controller import ManagerController
        from scripts.test_manager_controller import FakeSession
        sessions = []

        def factory(emit):
            session = FakeSession(emit)
            sessions.append(session)
            self.addCleanup(session.release.set)
            return session

        source_root = str(Path.cwd() / 'manager-source-fixture')
        self.window.variables["source_root"].set(source_root)
        controller = ManagerController(self.root, lambda *_args, **_kwargs: self.window, source_root,
                                       session_factory=factory, browser_opener=lambda _url: True)
        self.window.on_action, self.window.on_stop = controller.action, controller.stop
        self.window.action_buttons["start"].invoke()
        self.assertTrue(sessions[0].started.wait(1))
        start_id = next(iter(controller.tasks))
        self.window.action_buttons["test-sources"].invoke()
        self.assertTrue(sessions[1].started.wait(1))
        source_id = self.window.selected_task_id()
        self.assertNotEqual(start_id, source_id)
        self.assertTrue(all(str(button["state"]) == "normal" for button in self.window.action_buttons.values()))
        self.window.variables["source_root"].set("D:/edited")
        self.assertEqual(str(self.window._fields["source_root"]["state"]), "normal")
        self.assertEqual(controller.tasks[start_id].values["source_root"], source_root)
        controller.events.put({"task_id": start_id, "type": "input", "kind": "admin"})
        controller.events.put({"task_id": source_id, "type": "status", "message": "Kaynak denetimi sürüyor"})
        controller.poll()
        self.root.update_idletasks()
        self.assertIn(start_id, self.window._admin_dialogs)
        self.assertIsNone(self.root.grab_current())
        self.assertIn("Kaynak denetimi sürüyor", self.window.status_var.get())
        self.window.stop_button.invoke()
        self.assertTrue(sessions[1].stopped)
        self.assertFalse(sessions[0].stopped)
        self.window.dismiss_admin(start_id)
        self.assertEqual(sessions[0].sent, [])

    def test_task_rows_have_distinct_short_identifiers(self):
        self.window.update_tasks([
            {"id": "abc123-one", "action": "bundle", "profile": "dev", "status": "running", "values": {"output": "C:/one"}},
            {"id": "def456-two", "action": "bundle", "profile": "dev", "status": "running", "values": {"output": "C:/two"}},
        ])
        first = self.window.task_tree.item("abc123-one", "values")
        second = self.window.task_tree.item("def456-two", "values")
        self.assertNotEqual(first, second)
        self.assertIn("abc123", " ".join(first))
        self.assertIn("def456", " ".join(second))

    def test_open_ready_uses_controller_callback_with_selected_task(self):
        window = self.window
        window.update_tasks([{"id": "dev", "action": "start", "profile": "dev", "status": "ready", "values": {}}], selected_id="dev")
        window.handle_event({"task_id": "dev", "type": "ready", "url": "http://127.0.0.1:8000/app/"})
        opened = []
        window.on_open = lambda url, task_id: opened.append((url, task_id))
        with patch("webbrowser.open", side_effect=AssertionError("browser invoked on Tk thread")):
            window._open_ready()
        self.assertEqual(opened, [("http://127.0.0.1:8000/app/", "dev")])


if __name__ == "__main__":
    unittest.main()
