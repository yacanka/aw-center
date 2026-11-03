"""Native event bursts must not repeatedly repaint or disturb operator input."""

import tkinter as tk
from tkinter import ttk
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.manager.view import ManagerWindow


class NativeRenderingTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.window = ManagerWindow(self.root, lambda *_: None, lambda: None, lambda: None)
        self.window.update_tasks([
            {"id": "selected", "action": "doctor", "profile": "dev", "status": "running", "values": {}},
            {"id": "background", "action": "doctor", "profile": "prod", "status": "running", "values": {}},
        ], selected_id="selected")
        self.root.update()

    def test_status_burst_retains_events_with_one_scheduled_refresh(self):
        window = self.window
        with patch.object(window, "_refresh", wraps=window._refresh) as refresh:
            for index in range(200):
                window.handle_event({"task_id": "selected", "type": "status", "message": f"Kontrol {index}"})
            self.root.update_idletasks()
            self.assertEqual(refresh.call_count, 1)
        self.assertEqual(window.status_var.get(), "Kontrol 199")
        report = window.state.report()
        for index in range(200):
            self.assertIn(f"Kontrol {index}\n", report + "\n")

    def test_background_events_preserve_visible_report_selection_and_scroll(self):
        window = self.window
        for index in range(100):
            window.handle_event({"task_id": "selected", "type": "status", "message": f"Seçili rapor {index}"})
        window.tabs.select(window.report_tab)
        self.root.geometry("700x560")
        self.root.deiconify()
        self.root.update()
        window.report_text.yview_moveto(.4)
        self.root.update_idletasks()
        window.report_text.tag_add("sel", "1.0", "1.5")
        selected_range = window.report_text.tag_ranges("sel")
        viewport = window.report_text.yview()
        self.assertGreater(viewport[0], .1)
        with patch.object(window, "_refresh", wraps=window._refresh) as refresh:
            for index in range(200):
                window.handle_event({"task_id": "background", "type": "status", "message": f"Arka plan {index}"})
            self.root.update_idletasks()
            self.assertEqual(refresh.call_count, 0)
        self.assertEqual(window.report_text.tag_ranges("sel"), selected_range)
        self.assertEqual(window.report_text.yview(), viewport)
        self.assertEqual(window.selected_task_id(), "selected")
        self.assertIn("Arka plan 199", window.task_states.states["background"].report())

    def test_pending_refresh_follows_task_selection_without_mixing_reports(self):
        window = self.window
        window.tabs.select(window.report_tab)
        self.root.update()
        window.handle_event({"task_id": "selected", "type": "error", "message": "İlk görevin hatası"})
        window.handle_event({"task_id": "background", "type": "status", "message": "Diğer görevin raporu"})
        window.task_tree.selection_set("background")
        window._select_task()
        self.root.update()
        self.assertEqual(window.selected_task_id(), "background")
        report = window.report_text.get("1.0", "end")
        self.assertIn("Diğer görevin raporu", report)
        self.assertNotIn("İlk görevin hatası", report)
        self.assertEqual(window.error_var.get(), "")
        window.task_tree.selection_set("selected")
        window._select_task()
        self.root.update()
        self.assertIn("İlk görevin hatası", window.report_text.get("1.0", "end"))
        self.assertNotIn("Diğer görevin raporu", window.report_text.get("1.0", "end"))

    def test_hidden_report_opens_with_latest_safe_events(self):
        window = self.window
        window.handle_event({"task_id": "selected", "type": "status", "message": "Kontrol tamamlandı token=private-test-value"})
        self.root.update_idletasks()
        window.tabs.select(window.report_tab)
        self.root.update()
        report = window.report_text.get("1.0", "end")
        self.assertIn("Kontrol tamamlandı", report)
        self.assertNotIn("private-test-value", report)

    def test_unchanged_task_selection_does_not_generate_selection_callbacks(self):
        window = self.window
        callbacks = []
        window.task_tree.bind("<<TreeviewSelect>>", lambda _: callbacks.append(True), add=True)
        window._sync_task_selection()
        window._sync_task_selection()
        self.root.update()
        self.assertEqual(callbacks, [])

    def test_one_wheel_notch_scrolls_a_small_distance(self):
        window = self.window
        window._set_advanced(True)
        self.root.geometry("700x560")
        self.root.deiconify()
        self.root.update()
        panel = window.run_tab
        panel.canvas.yview_moveto(0)
        before = panel.canvas.canvasy(0)
        panel._wheel(SimpleNamespace(widget=window._fields["host"], num=5, delta=0))
        moved = panel.canvas.canvasy(0) - before
        self.assertGreater(moved, 0)
        self.assertLessEqual(moved, 48)

    def test_tab_repaints_stay_close_to_native_rendering_cost(self):
        # Compare identical visible tab interactions, so the budget scales with
        # the runner. A tiny tiled spacer made the themed tabs orders slower.
        top = tk.Toplevel(self.root)
        self.addCleanup(top.destroy)
        top.geometry("700x150")
        tabs = ttk.Notebook(top)
        tabs.pack(fill="both", expand=True)
        for label in ("Çalışma", "Paket kaynakları", "Durum ve rapor"):
            tabs.add(ttk.Frame(tabs), text=label)
        self.root.update()
        measurements = {}
        for style in ("TNotebook", "Manager.TNotebook"):
            tabs.configure(style=style)
            self.root.update_idletasks()
            started = time.process_time()
            for index in range(9):
                tabs.select(index % 3)
                self.root.update_idletasks()
            measurements[style] = time.process_time() - started
        self.assertLess(measurements["Manager.TNotebook"],
                        max(.08, measurements["TNotebook"] * 15), measurements)

    def test_long_status_keeps_form_viewport_usable(self):
        window = self.window
        self.root.geometry("700x560")
        self.root.deiconify()
        window.handle_event({"task_id": "selected", "type": "status", "message": "Paket denetimi sürüyor. " * 80})
        self.root.update()
        self.assertGreaterEqual(window.run_tab.canvas.winfo_height(), 100)
        self.assertIn("Paket denetimi sürüyor.", window.state.report())


if __name__ == "__main__":
    unittest.main()
