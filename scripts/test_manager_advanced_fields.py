"""Native visibility and value preservation for contextual Manager settings."""

import unittest
from unittest.mock import patch


class AdvancedFieldVisibilityTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
            from scripts.manager.view import ManagerWindow
        except ImportError as error:
            self.skipTest(f"Tk unavailable: {error}")
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(self.root.destroy)
        self.actions = []
        self.window = ManagerWindow(
            self.root, lambda action, values: self.actions.append((action, values)),
            lambda: None, lambda: None, source_root="C:/source")
        self.window._set_advanced(True)
        self.root.update()

    def field_widgets(self, key):
        from tkinter import ttk
        field = self.window._fields[key]
        labels = [widget for widget in field.master.winfo_children()
                  if isinstance(widget, ttk.Label)
                  and widget.cget("text") == self.window._field_titles[key]]
        self.assertEqual(len(labels), 1, key)
        return [*labels, field, *([self.window._pickers[key]] if key in self.window._pickers else [])]

    def assert_visible(self, widgets, visible):
        self.root.update_idletasks()
        for widget in widgets:
            with self.subTest(widget=str(widget)):
                self.assertEqual(bool(widget.winfo_viewable()), visible)

    def labels_starting_with(self, prefix):
        from tkinter import ttk
        return [widget for widget in self.window.advanced_frame.winfo_children()
                if isinstance(widget, ttk.Label) and widget.cget("text").startswith(prefix)]

    def test_profile_switch_hides_frontend_and_production_guidance_with_values_preserved(self):
        window = self.window
        frontend = self.field_widgets("frontend_port")
        tls = self.field_widgets("tls_cert_file") + self.field_widgets("tls_key_file")
        guidance = self.labels_starting_with("Yeni prod profili")
        self.assertEqual(len(guidance), 1)
        self.assert_visible(frontend, True)
        self.assert_visible(tls + guidance, False)
        window.variables["frontend_port"].set("15173")
        window.variables["tls_cert_file"].set("C:/private/server.crt")
        window.variables["tls_key_file"].set("C:/private/server.key")

        window.variables["profile"].set("prod")
        self.assert_visible(frontend, False)
        self.assert_visible(tls + guidance, True)
        window.action_buttons["start"].invoke()
        self.assertEqual(self.actions[-1][1]["frontend_port"], "")
        self.assertEqual(window.form_values()["frontend_port"], "15173")

        window.variables["profile"].set("dev")
        self.assert_visible(frontend, True)
        self.assert_visible(tls + guidance, False)
        self.assertEqual(window.form_values()["tls_cert_file"], "C:/private/server.crt")
        self.assertEqual(window.form_values()["tls_key_file"], "C:/private/server.key")
        window.action_buttons["start"].invoke()
        self.assertEqual(self.actions[-1][1]["frontend_port"], "15173")
        self.assertEqual(self.actions[-1][1]["tls_cert_file"], "")

    def test_managed_runtime_hides_its_manual_path_and_help_until_deselected(self):
        window = self.window
        rows = {
            "python": self.field_widgets("python_command") + self.labels_starting_with("Boşsa otomatik aranır."),
            "node": self.field_widgets("node_command") + self.labels_starting_with("Boşsa önce uygun sistem Node.js"),
        }
        window.variables["python_command"].set("C:/Python 311/python.exe")
        window.variables["node_command"].set("C:/Node 24/node.exe")
        for runtime, other in (("python", "node"), ("node", "python")):
            with self.subTest(runtime=runtime):
                self.assert_visible(rows[runtime], True)
                window.variables[f"install_{runtime}"].set(True)
                self.assert_visible(rows[runtime], False)
                self.assert_visible(rows[other], True)
                window.variables[f"install_{runtime}"].set(False)
                self.assert_visible(rows[runtime], True)
        self.assertEqual(window.form_values()["python_command"], "C:/Python 311/python.exe")
        self.assertEqual(window.form_values()["node_command"], "C:/Node 24/node.exe")

    def test_offline_hides_network_fields_and_preserves_local_inputs_and_other_modes(self):
        window = self.window
        window.tabs.select(window.source_tab)
        network_values = {
            "repository": "https://packages.example.test/runtime",
            "python_index_url": "https://packages.example.test/simple",
            "npm_registry_url": "https://npm.example.test",
            "ca_file": "C:/private/corporate.pem",
        }
        network_rows = {key: self.field_widgets(key) for key in network_values}
        for key, value in network_values.items():
            window.variables[key].set(value)
        window.variables["offline_dir"].set("D:/packages")
        window.variables["bundle_import"].set("D:/packages/runtime.zip")
        for mode in ("offline", "online", "offline", "corporate", "offline", "restricted"):
            with self.subTest(mode=mode):
                window.variables["source_mode"].set(mode)
                self.root.update()
                for key, widgets in network_rows.items():
                    self.assert_visible(widgets, key == 'ca_file' or mode != "offline")
                for key in ("offline_dir", "bundle_import", "assets", "feature_catalog", "output", "manager_distribution"):
                    self.assert_visible(self.field_widgets(key), True)
                for key, value in network_values.items():
                    self.assertEqual(window.form_values()[key], value)
        self.assertEqual(window.form_values()["offline_dir"], "D:/packages")
        self.assertEqual(window.form_values()["bundle_import"], "D:/packages/runtime.zip")

    def test_automatic_values_remain_empty_overrides_without_filesystem_probes(self):
        window = self.window
        window.variables["source_root"].set("")
        with patch("pathlib.Path.exists", side_effect=AssertionError("Tk must not probe paths")), \
                patch("pathlib.Path.resolve", side_effect=AssertionError("Tk must not resolve paths")):
            window.handle_event({"type": "profile", "profile": "dev", "status": "stopped",
                                 "source_root": "C:/installed/source"})
            for mode in ("offline", "corporate", "restricted"):
                window.variables["source_mode"].set(mode)
            for runtime in ("python", "node"):
                window.variables[f"install_{runtime}"].set(True)
                window.variables[f"install_{runtime}"].set(False)
            window.advanced_button.invoke()
            window.action_buttons["start"].invoke()
        self.assertIn("C:/installed/source", window.source_path_var.get())
        action, values = self.actions[-1]
        self.assertEqual(action, "ensure")
        for key in ("source_root", "host", "backend_port", "frontend_port", "python_command", "node_command",
                    "tls_cert_file", "tls_key_file", "env_file", "repository", "offline_dir",
                    "python_index_url", "npm_registry_url", "ca_file"):
            with self.subTest(field=key):
                self.assertEqual(values[key], "")


if __name__ == "__main__":
    unittest.main()
