"""Cancellation and containment regressions for desktop-managed operations."""
from pathlib import Path
import os
import subprocess
import sys
import textwrap
import threading
import unittest
from unittest.mock import patch

from scripts.launcher import process


class ManagerControlTests(unittest.TestCase):
    def run_with_open_control_pipe(self, statement):
        program = '''import os, sys, threading
from scripts.launcher import process
entered = threading.Event()
def controls():
    entered.set()
    os.read(sys.stdin.fileno(), 1)
threading.Thread(target=controls, daemon=True).start()
assert entered.wait(2)
'''
        child = subprocess.Popen([sys.executable, '-c', program + textwrap.dedent(statement)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            # communicate() would close stdin and remove the Manager condition.
            child.wait(timeout=10)
            output, errors = child.stdout.read(), child.stderr.read()
            self.assertEqual(child.returncode, 0, errors.decode('utf-8', errors='replace'))
            return output
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()

    def test_managed_command_gets_eof_without_consuming_control_pipe(self):
        output = self.run_with_open_control_pipe('''
            with process.operation_control(threading.Event()):
                result = process.controlled_run(
                    [sys.executable, '-c', 'import sys; print(repr(sys.stdin.buffer.read()))'],
                    capture_output=True, text=True, timeout=2, check=True)
            sys.stdout.write(result.stdout)
        ''')
        self.assertEqual(output.splitlines(), [b"b''"])

    def test_managed_command_preserves_explicit_input(self):
        with process.operation_control(threading.Event()):
            result = process.controlled_run(
                [sys.executable, '-c', 'import sys; print(sys.stdin.read())'],
                input='dedicated input', capture_output=True, text=True, timeout=5, check=True)
        self.assertEqual(result.stdout, 'dedicated input\n')

    def test_managed_command_preserves_explicit_stdin(self):
        import tempfile
        with tempfile.TemporaryFile() as source:
            source.write(b'dedicated stream')
            source.seek(0)
            with process.operation_control(threading.Event()):
                result = process.controlled_run(
                    [sys.executable, '-c', 'import sys; print(sys.stdin.read())'],
                    stdin=source, capture_output=True, text=True, timeout=5, check=True)
        self.assertEqual(result.stdout, 'dedicated stream\n')

    def test_worker_readiness_does_not_consume_control_pipe(self):
        output = self.run_with_open_control_pipe('''
            import tempfile
            from pathlib import Path
            from types import SimpleNamespace
            from scripts.launcher.installation import _worker_ready
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                script = root / 'health.py'
                script.write_text('import sys; assert sys.stdin.read() == ""', encoding='utf-8')
                project = SimpleNamespace(python=sys.executable, manage_py=script, root=root)
                assert _worker_ready(project, root), 'Health process could not finish with the control pipe open'
            print('ready')
        ''')
        self.assertEqual(output.splitlines(), [b'ready'])

    def test_frontend_keeps_all_nonsecret_bootstrap_pointers(self):
        tools = {'AWCENTER_MANAGED_PYTHON': '/managed/python.exe',
                 'AWCENTER_MANAGED_NODE': '/managed/node.exe',
                 'AWCENTER_MANAGED_NPM_CLI': '/managed/npm-cli.js'}
        with patch.dict(os.environ, {**tools, 'SECRET_KEY': 'not-a-real-secret'}, clear=True):
            with process.frontend_environment(True):
                self.assertEqual({key: os.environ.get(key) for key in tools}, tools)
                self.assertNotIn('SECRET_KEY', os.environ)

    def test_cancel_before_command_does_not_spawn(self):
        stop = threading.Event()
        stop.set()
        with process.operation_control(stop), patch.object(subprocess, 'Popen') as spawn:
            with self.assertRaises(process.OperationCancelled):
                process.controlled_run([sys.executable, '-c', 'pass'])
        spawn.assert_not_called()

    def test_cancel_running_command_reaps_owned_process(self):
        stop = threading.Event()
        timer = threading.Timer(0.2, stop.set)
        timer.start()
        try:
            with process.operation_control(stop):
                with self.assertRaises(process.OperationCancelled):
                    process.controlled_run([sys.executable, '-c', 'import time; time.sleep(30)'],
                                           capture_output=True, text=True, timeout=5)
        finally:
            timer.cancel()

    def test_cancellation_context_does_not_change_cli_runner(self):
        with patch.object(subprocess, 'run') as run:
            process.controlled_run(['example'], cwd=Path.cwd(), check=False)
        run.assert_called_once()

    def test_safe_boundary_waits_for_command_before_cancelling(self):
        stop = threading.Event()
        timer = threading.Timer(0.1, stop.set)
        timer.start()
        try:
            with process.operation_control(stop):
                with self.assertRaises(process.OperationCancelled):
                    process.controlled_run([sys.executable, '-c', 'import time; time.sleep(0.3)'],
                                           capture_output=True, safe_boundary=True, timeout=5)
        finally:
            timer.cancel()

    def test_supervision_observes_stop_request(self):
        stop = threading.Event()
        stop.set()
        with process.operation_control(stop), patch.object(process, 'terminate') as terminate:
            with self.assertRaises(process.OperationCancelled):
                process.supervise([unittest.mock.Mock()])
        terminate.assert_called_once()


if __name__ == '__main__':
    unittest.main()
