"""Desktop launch handoff and collision-safe shortcut creation."""
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, call, patch
from uuid import uuid4

from scripts.manager import desktop


class InstanceTests(unittest.TestCase):
    def setUp(self):
        self.kernel = Mock()
        self.kernel.CreateMutexW.return_value = 303
        self.kernel.CreateEventW.side_effect = [101, 102, 201, 202]
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(sys, 'platform', 'win32'))
        stack.enter_context(patch.object(desktop, '_kernel', return_value=self.kernel))
        stack.enter_context(patch.object(desktop, '_instance_name', return_value='Local\\test'))
        self.error = stack.enter_context(patch.object(desktop.ctypes, 'get_last_error', create=True))
        stack.enter_context(patch.object(desktop.ctypes, 'WinError', side_effect=OSError, create=True))

    def test_primary_owns_handles_and_consumes_activation_without_waiting(self):
        self.kernel.WaitForSingleObject.return_value = 0
        owner = desktop.acquire_instance()
        self.kernel.WaitForSingleObject.side_effect = [258, 258, 0, 258, 0]
        self.assertIsNone(owner.poll())
        self.assertEqual(owner.poll(), 'settings')
        self.assertEqual(owner.poll(), 'open')
        self.assertEqual(self.kernel.SetEvent.call_args_list, [call(102), call(202)])
        owner.close()
        owner.close()
        self.assertIsNone(owner.poll())
        self.assertCountEqual(self.kernel.CloseHandle.call_args_list,
                              [call(n) for n in [101, 102, 201, 202, 303]])
        self.kernel.ReleaseMutex.assert_called_once_with(303)

    def test_secondary_signals_requested_action_and_releases_handles(self):
        for settings, handle, ack in [(True, 101, 102), (False, 201, 202)]:
            with self.subTest(settings=settings):
                self.kernel.reset_mock()
                self.kernel.CreateEventW.side_effect = [101, 102, 201, 202]
                self.kernel.WaitForSingleObject.return_value = 258
                self.kernel.WaitForMultipleObjects.return_value = 0
                self.assertIsNone(desktop.acquire_instance(settings))
                self.kernel.SetEvent.assert_called_once_with(handle)
                self.kernel.ResetEvent.assert_called_once_with(ack)
                self.assertEqual(self.kernel.CloseHandle.call_count, 5)
                self.kernel.ReleaseMutex.assert_not_called()

    def test_secondary_takes_over_when_primary_exits_before_handling_request(self):
        for result in (1, 129):
            with self.subTest(wait_result=result):
                self.kernel.reset_mock()
                self.kernel.CreateEventW.side_effect = [101, 102, 201, 202]
                self.kernel.WaitForSingleObject.side_effect = [258, 0, 258, 258]
                self.kernel.WaitForMultipleObjects.return_value = result
                owner = desktop.acquire_instance(settings=True)
                self.assertIsNotNone(owner)
                self.assertIsNone(owner.poll())
                self.assertEqual(self.kernel.SetEvent.call_args_list, [call(101), call(102)])
                owner.close()
                self.kernel.ReleaseMutex.assert_called_once_with(303)

    def test_busy_owner_keeps_request_after_secondary_timeout(self):
        self.kernel.WaitForSingleObject.return_value = 258
        self.kernel.WaitForMultipleObjects.return_value = 258
        self.assertIsNone(desktop.acquire_instance())
        self.kernel.SetEvent.assert_called_once_with(201)
        self.kernel.ReleaseMutex.assert_not_called()

    def test_creation_or_signal_failure_closes_partial_state(self):
        self.kernel.CreateEventW.side_effect = [101, None]
        with self.assertRaises(OSError):
            desktop.acquire_instance()
        self.assertCountEqual(self.kernel.CloseHandle.call_args_list, [call(101), call(303)])
        self.kernel.CloseHandle.reset_mock()
        self.kernel.CreateEventW.side_effect = [101, 102, 201, 202]
        self.kernel.WaitForSingleObject.return_value = 258
        self.kernel.SetEvent.return_value = False
        with self.assertRaises(OSError):
            desktop.acquire_instance()
        self.assertEqual(self.kernel.CloseHandle.call_count, 5)

    def test_other_platforms_have_no_desktop_side_effects(self):
        with patch.object(sys, 'platform', 'darwin'):
            owner = desktop.acquire_instance()
            self.assertIsNone(owner.poll())
            owner.close()
            self.assertFalse(desktop.create_desktop_shortcut())
        self.kernel.CreateEventW.assert_not_called()


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.target = self.root / 'Manager folder' / 'AWCenterManager.exe'
        self.target.parent.mkdir()
        self.target.touch()
        self.destination = self.root / 'AW Center.lnk'
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(sys, 'platform', 'win32'))
        stack.enter_context(patch('_ctypes.COMError', OSError, create=True))
        stack.enter_context(patch.object(sys, 'executable', str(self.target)))
        stack.enter_context(patch.object(sys, 'frozen', True, create=True))
        stack.enter_context(patch.object(desktop, '_desktop_directory', return_value=self.root))

    def test_shortcut_targets_actual_frozen_executable(self):
        def save(path, target, arguments, directory):
            self.assertEqual((target, arguments, directory), (self.target, '', self.target.parent))
            self.assertNotEqual(path, self.destination)
            path.write_bytes(b'test shortcut')
        with patch.object(desktop, '_save_shortcut', side_effect=save):
            self.assertTrue(desktop.create_desktop_shortcut())
        self.assertEqual(self.destination.read_bytes(), b'test shortcut')

    def test_existing_shortcut_is_only_inspected_and_never_overwritten(self):
        self.destination.write_bytes(b'existing')
        for matches in (False, True):
            with self.subTest(matches=matches), patch.object(desktop, '_matches_shortcut', return_value=matches) as match, \
                    patch.object(desktop, '_save_shortcut') as save:
                self.assertIs(desktop.create_desktop_shortcut(), matches)
                match.assert_called_once_with(self.destination, self.target, '')
                save.assert_not_called()
                self.assertEqual(self.destination.read_bytes(), b'existing')

    def test_source_target_uses_windowless_python_and_quotes_script_path(self):
        script = self.root / 'Source & files' / 'AWCenterManager.pyw'
        script.parent.mkdir()
        script.touch()
        module = script.parent / 'scripts' / 'manager' / 'desktop.py'
        with patch.object(sys, 'frozen', False), patch.object(desktop, '__file__', str(module)):
            target, arguments, directory = desktop._shortcut_target()
            self.assertEqual(target, self.target.with_name('pythonw.exe'))
            self.assertEqual(arguments, f'"{script}"')
            self.assertEqual(directory, script.parent)
            self.assertFalse(desktop.create_desktop_shortcut())

    def test_symlink_or_reparse_shortcut_is_not_loaded(self):
        with patch.object(Path, 'lstat', return_value=Mock(st_mode=0o100644, st_reparse_tag=0xa000000c)), \
                patch.object(desktop, '_shell_link') as shell:
            self.assertFalse(desktop._matches_shortcut(self.destination, self.target, ''))
            shell.assert_not_called()

    def test_failed_save_leaves_no_partial_shortcut(self):
        def fail(path, *_):
            path.write_bytes(b'incomplete')
            raise PermissionError()
        with patch.object(desktop, '_save_shortcut', side_effect=fail):
            self.assertFalse(desktop.create_desktop_shortcut())
        self.assertEqual(list(self.root.iterdir()), [self.target.parent])


@unittest.skipUnless(os.name == 'nt', 'requires Windows kernel and shell')
class WindowsDesktopTests(unittest.TestCase):
    def test_native_activation_across_processes_then_restart(self):
        name = desktop._instance_name() + '.' + uuid4().hex
        self.assertTrue(name.startswith('Local\\AWCenterManager.'))
        child = ('from scripts.manager import desktop\n'
                 'import sys\n'
                 'desktop._instance_name = lambda: sys.argv[1]\n'
                 'assert desktop.acquire_instance(settings=True) is None\n')
        with patch.object(desktop, '_instance_name', return_value=name):
            primary = desktop.acquire_instance()
            try:
                with subprocess.Popen([sys.executable, '-c', child, name],
                                      cwd=Path(__file__).resolve().parents[1]) as process:
                    deadline = time.monotonic() + 10
                    action = None
                    while action is None and time.monotonic() < deadline:
                        action = primary.poll()
                        time.sleep(0.01)
                    self.assertEqual(action, 'settings')
                    self.assertEqual(process.wait(timeout=5), 0)
                    self.assertIsNone(primary.poll())
            finally:
                primary.close()
            restarted = desktop.acquire_instance()
            self.assertIsNotNone(restarted)
            restarted.close()

    def test_native_shutdown_handoff_without_poll_ack(self):
        name = desktop._instance_name() + '.' + uuid4().hex
        child = ('from scripts.manager import desktop\n'
                 'import sys\n'
                 'desktop._instance_name = lambda: sys.argv[1]\n'
                 'owner = desktop.acquire_instance()\n'
                 'assert owner is not None\n'
                 'owner.close()\n')
        with patch.object(desktop, '_instance_name', return_value=name):
            primary = desktop.acquire_instance()
            try:
                with subprocess.Popen([sys.executable, '-c', child, name],
                                      cwd=Path(__file__).resolve().parents[1]) as process:
                    # Observe its request but exit before the Tk callback acknowledges it.
                    self.assertEqual(primary._kernel.WaitForSingleObject(primary._events['open'], 5000), 0)
                    primary.close()
                    self.assertEqual(process.wait(timeout=5), 0)
            finally:
                primary.close()

    def test_native_shell_link_round_trip_and_foreign_file_preservation(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(desktop, '_desktop_directory', return_value=Path(temporary)):
            target = Path(sys.executable)
            args = '"C:\\Test Folder\\test.pyw"'
            with patch.object(desktop, '_shortcut_target', return_value=(target, args, target.parent)):
                self.assertTrue(desktop.create_desktop_shortcut())
                self.assertTrue(desktop.create_desktop_shortcut())
            destination = Path(temporary) / 'AW Center.lnk'
            original = destination.read_bytes()
            with patch.object(desktop, '_shortcut_target', return_value=(target, '', target.parent)):
                self.assertFalse(desktop.create_desktop_shortcut())
            self.assertEqual(destination.read_bytes(), original)
            destination.write_bytes(b'unrelated')
            self.assertFalse(desktop.create_desktop_shortcut())
            self.assertEqual(destination.read_bytes(), b'unrelated')
