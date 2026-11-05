"""Provisioning preserves incompatible virtual environments before rebuilding."""
import json
import io
import os
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.launcher import installation_dependencies as deps
from scripts.launcher.model import LauncherError, Project
from scripts.launcher.process import OperationCancelled
from scripts.launcher_test_support import create_project


class VenvRepairTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = create_project(self.root)
        self.selected = self.root / 'selected-python.exe'
        self.selected.write_bytes(b'validated interpreter')
        self.tools = {'AWCENTER_MANAGED_PYTHON': str(self.selected)}
        self.project.python.parent.mkdir(parents=True)
        self.project.python.write_bytes(b'old executable')
        (self.project.venv / 'preserved.py').write_bytes(b'original environment')
        self.base = self.root / 'previous-python.exe'
        self.version = 'True'
        self.creation_error = None

    def capture(self, command, project, overrides=None, **kwargs):
        if command[1:3] == ['-m', 'venv']:
            self.assertEqual(Path(command[0]), self.selected)
            self.assertEqual(Path(command[3]), self.project.venv)
            if self.creation_error is not None:
                raise self.creation_error
            self.project.python.parent.mkdir(parents=True, exist_ok=True)
            self.project.python.write_bytes(b'new executable')
            self.base = self.selected
            self.version = 'True'
        output = json.dumps(str(self.base)) if '_base_executable' in str(command) else self.version
        return subprocess.CompletedProcess(command, 0, output, '')

    def repair(self):
        with patch.object(deps, 'capture', side_effect=self.capture):
            deps._ensure_venv(self.project, self.tools, expected_python=self.selected,
                              repair=True)

    def backups(self):
        return list((self.project.root / '.runtime' / 'venv-backups').glob('*/.venv'))

    def test_different_interpreter_is_rebuilt_without_losing_old_environment(self):
        before = (self.project.venv / 'preserved.py').read_bytes()
        self.repair()
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'preserved.py').read_bytes(), before)
        self.assertEqual(self.project.python.read_bytes(), b'new executable')
        self.assertFalse((self.project.venv / 'preserved.py').exists())
        self.assertFalse((self.project.venv / '.awcenter-creating.json').exists())

    def test_matching_interpreter_reuses_existing_environment(self):
        self.base = self.selected
        self.repair()
        self.assertEqual(self.project.python.read_bytes(), b'old executable')
        self.assertEqual(self.backups(), [])

    def test_previous_windowed_creation_resumes_without_archiving_healthy_environment(self):
        self.selected = self.root / 'python.exe'
        self.selected.touch()
        windowed = self.root / 'pythonw.exe'
        windowed.touch()
        self.tools['AWCENTER_MANAGED_PYTHON'] = str(self.selected)
        self.base = self.selected
        marker = self.project.venv / '.awcenter-creating.json'
        marker.write_text(json.dumps({'version': 1, 'python': str(windowed),
                                      'source': str(self.project.root)}))
        with patch.object(sys, 'platform', 'win32'):
            self.repair()
        self.assertEqual(self.project.python.read_bytes(), b'old executable')
        self.assertEqual(self.backups(), [])
        self.assertFalse(marker.exists())

    def test_hardlinked_interpreter_alias_reuses_existing_environment(self):
        os.link(self.selected, self.base)
        self.repair()
        self.assertEqual(self.project.python.read_bytes(), b'old executable')
        self.assertEqual(self.backups(), [])

    def test_incomplete_unknown_environment_is_preserved_and_rebuilt(self):
        self.project.python.unlink()
        self.repair()
        self.assertEqual(self.project.python.read_bytes(), b'new executable')
        self.assertEqual((self.backups()[0] / 'preserved.py').read_bytes(), b'original environment')

    def test_wrong_python_version_is_preserved_and_rebuilt(self):
        self.version = 'False'
        self.repair()
        self.assertEqual(self.project.python.read_bytes(), b'new executable')
        self.assertEqual(len(self.backups()), 1)

    def test_foreign_interrupted_environment_is_preserved_and_rebuilt(self):
        marker = self.project.venv / '.awcenter-creating.json'
        marker.write_text(json.dumps({'version': 1, 'python': 'other', 'source': 'old source'}))
        before = marker.read_bytes()
        self.repair()
        self.assertEqual((self.backups()[0] / marker.name).read_bytes(), before)
        self.assertEqual(self.project.python.read_bytes(), b'new executable')

    def test_failed_creation_is_resumable_without_another_backup(self):
        self.creation_error = deps.PackageTimeoutError()
        with self.assertRaises(deps.PackageTimeoutError):
            self.repair()
        backup = self.backups()[0]
        self.assertEqual((backup / 'preserved.py').read_bytes(), b'original environment')
        self.assertTrue((self.project.venv / '.awcenter-creating.json').is_file())
        self.creation_error = None
        self.repair()
        self.assertEqual(self.backups(), [backup])
        self.assertEqual(self.project.python.read_bytes(), b'new executable')

    def test_failed_replacement_validation_does_not_repeat_backups(self):
        for failure in ('python_mismatch', 'version', 'unusable'):
            with self.subTest(failure=failure):
                original_capture = self.capture
                def still_invalid(command, *args, **kwargs):
                    result = original_capture(command, *args, **kwargs)
                    if self.project.python.read_bytes() == b'new executable':
                        if failure == 'unusable' and '-c' in command:
                            raise OSError(8, 'private diagnostic')
                        if failure == 'version' and 'struct' in str(command):
                            return subprocess.CompletedProcess(command, 0, 'False', '')
                        if failure == 'python_mismatch' and '_base_executable' in str(command):
                            value = str(self.root / 'different-python.exe')
                            return subprocess.CompletedProcess(command, 0,
                                json.dumps(value) if 'json.dumps' in str(command) else value, '')
                    return result
                # Each case starts with one unknown environment to preserve.
                self.project.python.write_bytes(b'old executable')
                self.base = self.root / 'previous-python.exe'
                marker = self.project.venv / '.awcenter-creating.json'
                marker.unlink(missing_ok=True)
                before = len(self.backups())
                with patch.object(deps, 'capture', side_effect=still_invalid):
                    for attempt in range(3):
                        with self.assertRaises(deps.VirtualEnvironmentError):
                            deps._ensure_venv(self.project, self.tools, expected_python=self.selected, repair=True)
                        self.assertEqual(len(self.backups()), before + 1, f'Retry {attempt} archived the replacement')
                        self.assertTrue(marker.exists())
                self.base, self.version = self.selected, 'True'
                self.repair()
                self.assertEqual(len(self.backups()), before + 1)
                self.assertFalse(marker.exists())

    def test_unicode_base_path_survives_windows_stdio_code_page(self):
        self.selected = self.root / 'Python-İş-中文' / 'python.exe'
        self.selected.parent.mkdir()
        self.selected.touch()
        self.tools['AWCENTER_MANAGED_PYTHON'] = str(self.selected)
        def probe(command, *args, **kwargs):
            code = command[command.index('-c') + 1]
            raw = io.BytesIO()
            output = io.TextIOWrapper(raw, encoding='cp1252', errors='strict')
            try:
                with patch.object(sys, '_base_executable', str(self.selected)), redirect_stdout(output):
                    exec(code, {})
                output.flush()
                value = raw.getvalue().decode('utf-8')
            except UnicodeError:
                return subprocess.CompletedProcess(command, 1, '', 'encoding failure')
            return subprocess.CompletedProcess(command, 0, value, '')
        with patch.object(deps, 'capture', side_effect=probe):
            deps._ensure_venv(self.project, self.tools, expected_python=self.selected)
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.project.python.read_bytes(), b'old executable')

    def test_cancellation_does_not_archive_existing_environment(self):
        with patch.object(deps, 'capture', side_effect=OperationCancelled('stopped')):
            with self.assertRaises(OperationCancelled):
                deps._ensure_venv(self.project, self.tools, expected_python=self.selected,
                                  repair=True)
        self.assertEqual(self.project.python.read_bytes(), b'old executable')
        self.assertEqual(self.backups(), [])

    def test_repair_cannot_move_its_selected_interpreter(self):
        self.selected = self.project.python
        self.tools['AWCENTER_MANAGED_PYTHON'] = str(self.selected)
        with self.assertRaises(LauncherError):
            self.repair()
        self.assertEqual(self.project.python.read_bytes(), b'old executable')
        self.assertEqual(self.backups(), [])

    def test_repair_cannot_move_the_running_manager_interpreter(self):
        with patch('sys.executable', str(self.project.python)):
            with self.assertRaises(LauncherError):
                self.repair()
        self.assertEqual(self.project.python.read_bytes(), b'old executable')
        self.assertEqual(self.backups(), [])

    def test_missing_replacement_interpreter_keeps_existing_environment(self):
        self.selected.unlink()
        with self.assertRaises(LauncherError):
            self.repair()
        self.assertEqual(self.project.python.read_bytes(), b'old executable')
        self.assertEqual(self.backups(), [])

    def test_unusable_existing_executable_is_preserved_and_rebuilt(self):
        def capture(command, *args, **kwargs):
            if self.project.python.is_file() and self.project.python.read_bytes() == b'old executable':
                raise OSError(8, 'wrong executable format')
            return self.capture(command, *args, **kwargs)
        with patch.object(deps, 'capture', side_effect=capture):
            deps._ensure_venv(self.project, self.tools, expected_python=self.selected, repair=True)
        self.assertEqual(self.project.python.read_bytes(), b'new executable')
        self.assertEqual(len(self.backups()), 1)

    def test_real_interpreter_recreates_incomplete_environment_with_working_pip(self):
        self.project.python.unlink()
        selected = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        deps._ensure_venv(self.project, {'AWCENTER_MANAGED_PYTHON': str(selected)},
                          expected_python=selected, repair=True)
        result = subprocess.run([self.project.python, '-I', '-c',
                                 'import pip, sys; print(sys.prefix)'],
                                capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(Path(result.stdout.strip()).resolve(), self.project.venv)
        self.assertEqual((self.backups()[0] / 'preserved.py').read_bytes(), b'original environment')
        self.assertFalse((self.project.venv / '.awcenter-creating.json').exists())

    def test_backup_parent_link_is_rejected_without_touching_environment(self):
        destination = self.root / 'elsewhere'
        destination.mkdir()
        try:
            (self.root / '.runtime').symlink_to(destination, target_is_directory=True)
        except OSError:
            self.skipTest('symlink privilege unavailable')
        with self.assertRaises(LauncherError):
            self.repair()
        self.assertEqual(self.project.python.read_bytes(), b'old executable')
        self.assertEqual(list(destination.iterdir()), [])

    def test_backup_rename_failure_keeps_existing_environment_and_reports_safe_error(self):
        with patch.object(Path, 'rename', side_effect=PermissionError(13, 'sensitive path')):
            with self.assertRaises(LauncherError) as caught:
                self.repair()
        self.assertEqual(caught.exception.code, 'venv_repair_failed')
        self.assertNotIn('sensitive path', str(caught.exception))
        self.assertEqual(self.project.python.read_bytes(), b'old executable')

    def test_repair_preserves_source_manifest_and_excludes_backup_from_new_payload(self):
        from scripts.manager.payload import (REQUIRED_SOURCE_FILES, prepare_source_payload,
                                             verify_source_payload)
        for relative in REQUIRED_SOURCE_FILES:
            path = self.root / relative
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# fixture\n')
        source = self.root / 'release'
        before = prepare_source_payload(self.project, source)
        self.project = Project(source, source / 'backend/manage.py',
                               source / 'frontend/package.json', source / 'requirements.txt')
        self.project.python.parent.mkdir(parents=True)
        self.project.python.write_bytes(b'old executable')
        (self.project.venv / 'preserved.py').write_bytes(b'original environment')
        self.repair()
        self.assertEqual(verify_source_payload(source), before)
        copied = self.root / 'copied-release'
        prepare_source_payload(self.project, copied)
        self.assertFalse((copied / '.runtime').exists())
        self.assertFalse((copied / '.venv').exists())
        self.assertEqual((self.backups()[0] / 'preserved.py').read_bytes(), b'original environment')

    def test_only_manager_provisioning_automatically_repairs_existing_environment(self):
        from scripts.launcher import installation
        from scripts.launcher.installation_sources import SourceSettings

        class DependenciesPrepared(Exception):
            pass

        for flags in ({}, {'manager_ensure': True}, {'manager_repair_venv': True}):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                self.project = create_project(Path(temporary).resolve())
                self.project.python.parent.mkdir(parents=True)
                self.project.python.write_bytes(b'old executable')
                self.base = self.root / 'previous-python.exe'
                args = SimpleNamespace(profile='dev', **flags)
                stack.enter_context(patch.object(installation, 'require_windows'))
                stack.enter_context(patch.object(installation, 'installation_home', return_value=self.root / 'private'))
                stack.enter_context(patch.object(installation, 'source_settings', return_value=SourceSettings()))
                stack.enter_context(patch('scripts.launcher.runtime_selection.tool_choices', return_value={}))
                stack.enter_context(patch.object(installation, 'ensure_toolchain',
                                              return_value={**self.tools, 'AWCENTER_MANAGED_NODE': '/node'}))
                stack.enter_context(patch.object(deps, 'capture', side_effect=self.capture))
                stack.enter_context(patch.object(deps, 'package_trust_environment', side_effect=DependenciesPrepared))
                if flags:
                    with self.assertRaises(DependenciesPrepared):
                        installation.provision(self.project, args)
                    self.assertEqual(self.project.python.read_bytes(), b'new executable')
                    self.assertEqual(len(self.backups()), 1)
                else:
                    with self.assertRaises(LauncherError):
                        installation.provision(self.project, args)
                    self.assertEqual(self.project.python.read_bytes(), b'old executable')
                    self.assertEqual(self.backups(), [])


if __name__ == '__main__':
    unittest.main()
