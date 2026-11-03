"""Cancellation and containment regressions for desktop-managed operations."""
from pathlib import Path
import os
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from scripts.launcher import process


class ManagerControlTests(unittest.TestCase):
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
