"""Scoped startup work evidence contains only fixed operation counts."""
import threading
from pathlib import Path
import tempfile
import unittest


class StartupMetricsTests(unittest.TestCase):
    def test_actual_source_inventory_is_counted(self):
        from scripts.launcher.startup_metrics import startup_work
        from scripts.manager.payload import _source_inventory
        events = []
        with tempfile.TemporaryDirectory() as directory, startup_work(events.append):
            self.assertEqual(_source_inventory(Path(directory)), [])
        self.assertEqual(events[-1]['counts']['source_inventory'], 1)

    def test_counts_are_scoped_and_published_before_readiness_without_paths(self):
        from scripts.launcher.startup_metrics import count_startup_work, emit_startup_work, startup_work
        events = []
        count_startup_work('dependency_inventory')
        with startup_work(events.append, 'developer'):
            count_startup_work('dependency_inventory')
            count_startup_work('source_inventory')
            emit_startup_work()
            self.assertEqual(events[-1]['counts']['dependency_inventory'], 1)
            self.assertEqual(events[-1]['counts']['source_inventory'], 1)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1]['policy'], 'developer')
        self.assertEqual(set(events[-1]), {'type', 'policy', 'counts'})
        with startup_work(events.append, 'managed'):
            emit_startup_work()
            self.assertFalse(any(events[-1]['counts'].values()))

    def test_unknown_counter_and_other_thread_cannot_pollute_current_request(self):
        from scripts.launcher.startup_metrics import count_startup_work, startup_work
        events = []
        with startup_work(events.append):
            count_startup_work('/private/operator-supplied-value')
            child = threading.Thread(target=count_startup_work, args=('runtime_inventory',))
            child.start()
            child.join()
        self.assertFalse(any(events[-1]['counts'].values()))

    def test_cancelled_operation_publishes_final_counts_and_resets_context(self):
        from scripts.launcher.startup_metrics import count_startup_work, emit_startup_work, startup_work
        events = []
        with self.assertRaises(RuntimeError), startup_work(events.append):
            count_startup_work('runtime_inventory')
            raise RuntimeError('cancelled')
        self.assertEqual(events[-1]['counts']['runtime_inventory'], 1)
        emit_startup_work()
        self.assertEqual(len(events), 1)
