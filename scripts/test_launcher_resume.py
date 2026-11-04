"""An owned interrupted venv can be completed without deleting existing state."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation_dependencies as deps
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project


class ResumeTests(unittest.TestCase):
    def test_completed_stage_is_reused_only_after_lock_and_files_are_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target, lock = root / 'packages', root / 'lock'
            lock.write_bytes(b'locked dependencies')
            calls = []
            def install():
                calls.append(True)
                target.mkdir(exist_ok=True)
                (target / 'package').write_bytes(b'installed')
            deps.dependency_stage(target, lock, install)
            deps.dependency_stage(target, lock, install)
            self.assertEqual(len(calls), 1)
            (target / 'package').write_bytes(b'changed')
            with self.assertRaises(LauncherError):
                deps.dependency_stage(target, lock, install)
            self.assertEqual(len(calls), 1, 'Changed completed files must not be silently overwritten')

    def test_owned_interrupted_creation_can_retry_same_python_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary).resolve())
            tools = {'AWCENTER_MANAGED_PYTHON': str(project.root / 'python.exe')}
            def partial(command, *args, **kwargs):
                project.venv.mkdir(exist_ok=True)
                (project.venv / 'preserved').write_bytes(b'keep')
                return subprocess.CompletedProcess(command, 1, '', '')
            with patch.object(deps, 'capture', side_effect=partial):
                with self.assertRaises(LauncherError):
                    deps._ensure_venv(project, tools)
            calls = []
            def finish(command, *args, **kwargs):
                calls.append(command)
                if '-m' in command and 'venv' in command:
                    project.python.parent.mkdir(parents=True, exist_ok=True)
                    project.python.touch()
                output = tools['AWCENTER_MANAGED_PYTHON'] if '_base_executable' in str(command) else 'True'
                return subprocess.CompletedProcess(command, 0, output, '')
            with patch.object(deps, 'capture', side_effect=finish):
                deps._ensure_venv(project, tools, expected_python=Path(tools['AWCENTER_MANAGED_PYTHON']))
            self.assertEqual((project.venv / 'preserved').read_bytes(), b'keep')
            self.assertTrue(any('venv' in command for command in calls))

    def test_unknown_incomplete_environment_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary).resolve())
            project.venv.mkdir()
            (project.venv / 'keep').write_bytes(b'private')
            with patch.object(deps, 'capture') as capture:
                with self.assertRaises(LauncherError):
                    deps._ensure_venv(project, {'AWCENTER_MANAGED_PYTHON': '/python'})
            capture.assert_not_called()
            self.assertEqual((project.venv / 'keep').read_bytes(), b'private')
