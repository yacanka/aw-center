"""Process containment distinguishes stopped executors from zombie metadata."""

import os
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.test import SimpleTestCase

from jobs.process_tree import ExecutorProcessTree


@skipUnless(sys.platform == "linux", "Linux process-state checks require /proc.")
class LinuxProcessTreeTests(SimpleTestCase):
    def start_process(self, code, *, process_group=None):
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            start_new_session=process_group is None,
            process_group=process_group,
        )
        self.addCleanup(self.stop_process, process)
        return process

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)

    def test_zombie_group_does_not_block_exit_confirmation(self):
        process = self.start_process("pass")
        # Observe exit without reaping it: killpg(..., 0) still sees this group.
        os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)
        os.killpg(process.pid, 0)

        tree = ExecutorProcessTree(process)

        self.assertTrue(tree.wait_for_exit(timeout=0))

    def test_live_group_still_blocks_exit_confirmation(self):
        process = self.start_process("import time; time.sleep(30)")
        tree = ExecutorProcessTree(process)

        self.assertFalse(tree.wait_for_exit(timeout=0))

    def test_live_member_still_blocks_exit_with_zombie_group_leader(self):
        leader = self.start_process("pass", process_group=0)
        os.waitid(os.P_PID, leader.pid, os.WEXITED | os.WNOWAIT)
        self.start_process("import time; time.sleep(30)", process_group=leader.pid)
        tree = ExecutorProcessTree(leader)

        self.assertFalse(tree.wait_for_exit(timeout=0))

    def test_live_threads_still_block_exit_with_zombie_process_leader(self):
        process = self.start_process(
            "import ctypes, threading, time; "
            "threading.Thread(target=lambda: time.sleep(30)).start(); "
            "ctypes.CDLL(None).pthread_exit(None)"
        )
        status_file = Path(f"/proc/{process.pid}/stat")
        deadline = time.monotonic() + 5
        state = ""
        while time.monotonic() < deadline:
            state = status_file.read_text().rpartition(")")[2].split()[0]
            if state == "Z":
                break
            time.sleep(0.01)
        self.assertEqual(state, "Z", "The leader must exit while its thread remains alive.")

        tree = ExecutorProcessTree(process)

        self.assertFalse(tree.wait_for_exit(timeout=0))

    def test_unreadable_thread_state_cannot_confirm_group_exit(self):
        process = self.start_process("pass")
        os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)
        tree = ExecutorProcessTree(process)
        scandir = os.scandir

        def unreadable_tasks(path):
            if str(path).endswith("/task"):
                raise PermissionError
            return scandir(path)

        with patch("jobs.process_tree.os.scandir", side_effect=unreadable_tasks):
            self.assertFalse(tree.wait_for_exit(timeout=0))

    def test_unreadable_process_state_cannot_confirm_group_exit(self):
        process = self.start_process("pass")
        os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)
        tree = ExecutorProcessTree(process)

        with patch("jobs.process_tree.os.scandir", side_effect=PermissionError):
            self.assertFalse(tree.wait_for_exit(timeout=0))

    def test_group_missing_from_procfs_cannot_confirm_exit_while_killpg_sees_it(self):
        process = self.start_process("pass")
        os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)
        tree = ExecutorProcessTree(process)

        with patch("jobs.process_tree.os.scandir", return_value=nullcontext([])):
            self.assertFalse(tree.wait_for_exit(timeout=0))
