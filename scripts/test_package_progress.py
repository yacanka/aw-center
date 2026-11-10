"""Live package output must arrive before exit and never expose source details."""
import subprocess
import sys
import threading
import unittest

from scripts.launcher.process import controlled_run, operation_control, OperationCancelled
from scripts.launcher import installation_dependencies as deps


class PackageProgressTests(unittest.TestCase):
    def test_output_arrives_before_exit_and_remains_captured(self):
        # The child cannot finish until the callback creates its acknowledgement.
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            ack = Path(directory) / 'ack'
            lines = []
            def progress(line):
                lines.append(line)
                ack.touch()
            code = ('import pathlib,sys,time; print("Collecting Django==5.2", flush=True); '
                    'p=pathlib.Path(sys.argv[1]); '
                    '\nwhile not p.exists(): time.sleep(.01)\n'
                    'print("diagnostic", file=sys.stderr, flush=True)')
            with operation_control(threading.Event()):
                result = controlled_run([sys.executable, '-u', '-c', code, str(ack)],
                                        capture_output=True, text=True, timeout=5, on_output=progress)
            self.assertIn('Collecting Django==5.2', ''.join(lines))
            self.assertEqual(result.stdout, 'Collecting Django==5.2\n')
            self.assertEqual(result.stderr, 'diagnostic\n')

    def test_streaming_cancellation(self):
        stop = threading.Event()
        with operation_control(stop), self.assertRaises(OperationCancelled):
            controlled_run([sys.executable, '-u', '-c',
                            'import time; print("ready", flush=True); time.sleep(30)'],
                           capture_output=True, text=True, timeout=5,
                           on_output=lambda line: stop.set())

    def test_streaming_timeout(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            controlled_run([sys.executable, '-c', 'import time; time.sleep(30)'],
                           capture_output=True, text=True, timeout=.1, on_output=lambda line: None)

    def test_capture_routes_safe_events_into_manager_report(self):
        import tempfile
        from pathlib import Path
        from scripts.launcher_test_support import create_project
        from scripts.manager.view_model import ManagerState
        state = ManagerState()
        program = ('import sys; print("Collecting Django==5.2", flush=True); '
                   'print("Downloading Django-5.2-py3-none-any.whl (8.3 MB)", flush=True); '
                   'print("https://user:password@example.invalid", file=sys.stderr); '
                   'sys.exit(7)')
        with tempfile.TemporaryDirectory() as directory:
            result = deps.capture([sys.executable, '-c', program], create_project(Path(directory)),
                                  progress=lambda text: state.handle_event({'type': 'phase', 'message': text}))
        self.assertEqual(result.returncode, 7)
        self.assertIn('Django-5.2-py3-none-any.whl', state.status)
        self.assertNotIn('password', state.status)
        self.assertEqual(len(state.phases), 2)
        self.assertIn('password', result.stderr)  # Diagnostics stay private for error classification.

    def test_only_reviewed_package_details_are_reported(self):
        examples = {
            'Collecting Django==5.2 (from -r /private/requirements.txt (line 1))': 'Python: paket çözülüyor — Django==5.2',
            '  Downloading Django-5.2-py3-none-any.whl (8.3 MB)': 'Python: indiriliyor — Django-5.2-py3-none-any.whl (8.3 MB)',
            '  Using cached Django-5.2-py3-none-any.whl (8.3 MB)': 'Python: önbellekten alınıyor — Django-5.2-py3-none-any.whl (8.3 MB)',
            '  Building wheel for example (pyproject.toml): started': 'Python: wheel derleniyor — example',
            'Installing collected packages: sqlparse, Django': 'Python: kuruluyor — sqlparse, Django',
        }
        for raw, expected in examples.items():
            self.assertEqual(deps.python_package_progress(raw), expected)
        for raw in ('Looking in indexes: https://user:password@example.invalid/simple',
                    'Downloading https://example.invalid/private.whl?token=secret',
                    'Collecting https://example.invalid/private.whl',
                    'ERROR: token=secret', 'Installing collected packages: secret=https://private',
                    'Downloading /private/file.whl', 'Collecting name@https://private'):
            self.assertIsNone(deps.python_package_progress(raw))
