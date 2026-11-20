"""Server output gets one console without moving Manager's private IPC streams."""
from contextlib import ExitStack
import ctypes
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.launcher import installation, process
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project


class ManagerServerConsoleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = create_project(self.root)
        self.profile = {'name': 'dev', 'host': '127.0.0.1', 'backend_port': 8000,
                        'frontend_port': 5173, 'installation_home': str(self.root / 'private'),
                        'env_file': str(self.root / 'private/config/dev.env')}
        self.console_path = self.root / 'console.log'
        self.console = self.console_path.open('w', encoding='utf-8', buffering=1)
        self.addCleanup(self.console.close)
        self.channel, self.control_input, self.discard = io.StringIO(), io.StringIO('control input'), io.StringIO()
        self.original_handles = {number & 0xffffffff: number + 200 for number in (-10, -11, -12)}
        self.handles = self.original_handles.copy()
        self.kernel = Mock()
        self.kernel.GetConsoleWindow.return_value = 0
        self.kernel.GetStdHandle.side_effect = self.handles.__getitem__
        def allocate():
            self.handles.update({number: 900 for number in self.handles})
            return True
        self.kernel.AllocConsole.side_effect = allocate
        def set_handle(number, value):
            self.handles[number] = value
            return True
        self.kernel.SetStdHandle.side_effect = set_handle
        self.kernel.FreeConsole.return_value = True
        self.code_page = 437
        self.kernel.GetConsoleOutputCP.side_effect = lambda: self.code_page
        def set_code_page(value):
            self.code_page = value
            return True
        self.kernel.SetConsoleOutputCP.side_effect = set_code_page
        self.child = Mock()
        self.child._handle = 42
        self.spawn = Mock(return_value=self.child)

    def patches(self, runtime):
        stack = ExitStack()
        stack.enter_context(patch.object(installation, 'require_windows'))
        stack.enter_context(patch.object(installation, 'load_profile', return_value=self.profile))
        stack.enter_context(patch.object(installation, 'profile_environment', return_value={}))
        stack.enter_context(patch('scripts.launcher.toolchain.toolchain_environment', return_value={}))
        stack.enter_context(patch('scripts.launcher.installation_features.feature_environment', return_value={}))
        stack.enter_context(patch.object(installation, '_django'))
        session = stack.enter_context(patch.object(installation, 'runtime_session'))
        session.return_value.__enter__.return_value = self.root
        stack.enter_context(patch.object(installation.runtime, 'dev', side_effect=runtime))
        stack.enter_context(patch.object(process, 'os', SimpleNamespace(name='nt', environ=os.environ)))
        stack.enter_context(patch.object(ctypes, 'WinDLL', return_value=self.kernel, create=True))
        stack.enter_context(patch.dict(sys.modules, {'msvcrt': SimpleNamespace(get_osfhandle=lambda descriptor: descriptor + 1000)}))
        stack.enter_context(patch.object(process, 'open', return_value=self.console, create=True))
        stack.enter_context(patch.object(subprocess, 'CREATE_NEW_PROCESS_GROUP', 512, create=True))
        stack.enter_context(patch.object(subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True))
        stack.enter_context(patch.object(subprocess, 'Popen', self.spawn))
        stack.enter_context(patch('scripts.launcher.windows_job.WindowsJob'))
        stack.enter_context(patch.object(sys, 'stdout', self.discard))
        stack.enter_context(patch.object(sys, 'stderr', self.discard))
        stack.enter_context(patch.object(sys, 'stdin', self.control_input))
        stack.enter_context(process.operation_control(threading.Event()))
        return stack

    def launch(self):
        return process._start_windows(['server', '--serve'], self.project.root, {})

    def test_server_children_share_visible_output_while_protocol_and_stdin_stay_private(self):
        def runtime(*args, **kwargs):
            self.launch()
            self.launch()
            print('server stdout')
            sys.stderr.write('server stderr\n')
            self.channel.write('{"type":"ready"}\n')
            self.assertIs(sys.stdin, self.control_input)
            self.assertEqual(self.handles[-10 & 0xffffffff], self.original_handles[-10 & 0xffffffff])
            self.assertEqual(self.code_page, 65001)
        with self.patches(runtime):
            installation._start_profile(self.project, 'dev')
            self.assertIs(sys.stdout, self.discard)
            self.assertIs(sys.stderr, self.discard)
            self.assertIs(sys.stdin, self.control_input)
        self.kernel.AllocConsole.assert_called_once()
        self.kernel.FreeConsole.assert_called_once()
        self.assertEqual(self.handles, self.original_handles)
        self.assertEqual(self.code_page, 437)
        self.assertEqual(self.console_path.read_text(), 'server stdout\nserver stderr\n')
        self.assertEqual(self.channel.getvalue(), '{"type":"ready"}\n')
        self.assertEqual(self.control_input.read(), 'control input')
        for call in self.spawn.call_args_list:
            self.assertFalse(call.kwargs['creationflags'] & 0x08000000)
            self.assertIs(call.kwargs['stdout'], self.console)
            self.assertIs(call.kwargs['stderr'], self.console)
            self.assertEqual(call.kwargs['stdin'], subprocess.PIPE)

    def test_desktop_server_runs_hidden_and_contained(self):
        with self.patches(lambda *_, **__: self.launch()), process.operation_control(
                threading.Event(), hide_server_window=True):
            installation._start_profile(self.project, 'dev')
        self.kernel.AllocConsole.assert_not_called()
        self.assertTrue(self.spawn.call_args.kwargs['creationflags'] & 0x08000000)
        self.assertEqual(self.spawn.call_args.kwargs['stdout'], subprocess.DEVNULL)
        self.child.stdin.write.assert_called_once_with(b'go\n')

    def test_preflight_failure_never_allocates_a_console(self):
        with self.patches(lambda *args, **kwargs: self.fail('runtime started')), \
             patch.object(installation, '_django', side_effect=LauncherError('schema check failed')):
            with self.assertRaises(LauncherError):
                installation._start_profile(self.project, 'dev')
        self.kernel.AllocConsole.assert_not_called()
        self.spawn.assert_not_called()

    def test_runtime_gate_failure_before_first_server_never_allocates_a_console(self):
        def runtime(*args, **kwargs):
            self.kernel.AllocConsole.assert_not_called()
            raise LauncherError('port check failed')
        with self.patches(runtime):
            with self.assertRaises(LauncherError):
                installation._start_profile(self.project, 'dev')
        self.kernel.AllocConsole.assert_not_called()
        self.spawn.assert_not_called()

    def test_server_failure_restores_streams_handles_and_owned_console(self):
        def runtime(*args, **kwargs):
            self.launch()
            raise LauncherError('server failed')
        with self.patches(runtime):
            with self.assertRaises(LauncherError):
                installation._start_profile(self.project, 'dev')
            self.assertIs(sys.stdout, self.discard)
            self.assertIs(sys.stderr, self.discard)
            self.assertIs(sys.stdin, self.control_input)
        self.kernel.AllocConsole.assert_called_once()
        self.kernel.FreeConsole.assert_called_once()
        self.assertTrue(self.console.closed)
        self.assertEqual(self.handles, self.original_handles)

    def test_existing_console_is_reused_without_detaching_it(self):
        def runtime(*args, **kwargs):
            self.launch()
            print('shared console')
        with self.patches(runtime):
            self.kernel.GetConsoleWindow.return_value = 123
            installation._start_profile(self.project, 'dev')
        self.kernel.AllocConsole.assert_not_called()
        self.kernel.FreeConsole.assert_not_called()
        self.assertEqual(self.console_path.read_text(), 'shared console\n')

    def test_manager_helpers_remain_hidden_even_during_runtime_gates(self):
        def runtime(*args, **kwargs):
            helper = Mock(returncode=0)
            helper.communicate.return_value = (None, None)
            with patch.object(process, '_controlled_windows', return_value=helper) as spawn, \
                 patch.object(process, 'terminate'):
                process.controlled_run(['helper'], check=True)
            options = spawn.call_args.args[1]
            self.assertEqual(options['stdout'], subprocess.DEVNULL)
            self.assertEqual(options['stderr'], subprocess.DEVNULL)
            self.assertEqual(options['stdin'], subprocess.DEVNULL)
            self.assertTrue(options['creationflags'] & 0x08000000)
            self.kernel.AllocConsole.assert_not_called()
        with self.patches(runtime):
            installation._start_profile(self.project, 'dev')
        self.kernel.AllocConsole.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Requires native Windows console attachment, UTF-8 and Job Objects')
    def test_native_desktop_worker_stays_hidden_and_preserves_private_pipes(self):
        import json
        import textwrap
        program = textwrap.dedent('''\
            import ctypes, io, json, sys, threading
            from pathlib import Path
            from scripts.launcher import process
            kernel = ctypes.WinDLL('kernel32')
            kernel.GetConsoleWindow.restype = ctypes.c_void_p
            channel, control_input = sys.stdout, sys.stdin
            sys.stdout = io.StringIO()
            initial_window = kernel.GetConsoleWindow()
            with process.operation_control(threading.Event(), hide_server_window=True), process.server_console():
                assert kernel.GetConsoleWindow() == initial_window
                child = process.start([sys.executable, '-c',
                    'import time; print("Türkçe sunucu çıktısı", flush=True); time.sleep(30)'], Path.cwd())
                try:
                    window = kernel.GetConsoleWindow()
                    channel.write(json.dumps({'same_console': window == initial_window,
                        'hidden': not window or not ctypes.windll.user32.IsWindowVisible(ctypes.c_void_p(window)),
                        'stdin_unchanged': sys.stdin is control_input,
                        'input': control_input.buffer.read().decode('utf-8')}) + '\\n')
                    channel.flush()
                finally:
                    process.terminate([child])
            channel.write(json.dumps({'restored': kernel.GetConsoleWindow() == initial_window}) + '\\n')
            channel.flush()
        ''')
        console_python = str(Path(sys.executable).with_name('python.exe'))
        completed = subprocess.run([console_python, '-c', program], cwd=Path(__file__).resolve().parents[1],
                                   input='private control input', capture_output=True, text=True, encoding='utf-8',
                                   timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual([json.loads(line) for line in completed.stdout.splitlines()],
                         [{'same_console': True, 'hidden': True, 'stdin_unchanged': True,
                           'input': 'private control input'}, {'restored': True}])


if __name__ == '__main__':
    unittest.main()
