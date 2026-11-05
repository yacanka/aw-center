"""Exercise real Windows Python identity through the Manager's command gate."""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.launcher import installation_dependencies as deps
from scripts.launcher.process import operation_control
from scripts.launcher.system_python import validate_python
from scripts.launcher_test_support import create_project


@unittest.skipUnless(os.name == 'nt', 'Requires native Windows CPython and Job Objects')
class WindowsPythonIdentityTests(unittest.TestCase):
    def test_pythonw_selection_repairs_once_and_reuses_unicode_path_environment(self):
        self.assertEqual(sys.version_info[:2], (3, 11))
        expected_version = os.environ.get('AWCENTER_EXPECT_PYTHON_VERSION')
        if expected_version:
            self.assertEqual('.'.join(map(str, sys.version_info[:3])), expected_version)
        base = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        with tempfile.TemporaryDirectory(prefix='AW Center Python İışğ ') as temporary:
            root = Path(temporary).resolve()
            installation = root / 'Python kurulumu ŞĞ'
            installation.mkdir()
            # Copy the installed standard runtime so both the selected base
            # interpreter and the environment contain non-ASCII path segments.
            # Application packages are irrelevant and can make CI copies huge.
            for source in base.parent.iterdir():
                if source.is_file() and source.suffix.lower() in {'.exe', '.dll'}:
                    shutil.copy2(source, installation / source.name)
            for name in ('DLLs', 'Lib'):
                shutil.copytree(base.parent / name, installation / name,
                                ignore=shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc'))
            project_root = root / 'AW Center kaynak çığ'
            project_root.mkdir()
            project = create_project(project_root)
            project.venv.mkdir()
            (project.venv / 'preserved.txt').write_text('original environment', encoding='utf-8')

            with patch.object(sys, 'executable', str(installation / 'pythonw.exe')), \
                    operation_control(threading.Event()):
                selected = validate_python(installation / 'pythonw.exe')
                self.assertTrue(selected.samefile(installation / 'python.exe'))
                tools = {'AWCENTER_MANAGED_PYTHON': str(selected)}
                for attempt in range(2):
                    with self.subTest(attempt=attempt):
                        deps._ensure_venv(project, tools, expected_python=selected, repair=True)
                        backups = list((project.root / '.runtime/venv-backups').glob('*/.venv'))
                        self.assertEqual(len(backups), 1)
                        self.assertEqual((backups[0] / 'preserved.txt').read_text(encoding='utf-8'),
                                         'original environment')
                        self.assertFalse((project.venv / '.awcenter-creating.json').exists())
                result = deps.capture(
                    [project.python, '-I', '-B', '-c',
                     'import json,pip,sys; print(json.dumps({"prefix": sys.prefix, '
                     '"base": sys._base_executable}, ensure_ascii=True))'],
                    project, tools, timeout=60,
                )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            identity = json.loads(result.stdout)
            self.assertEqual(Path(identity['prefix']).resolve(), project.venv)
            self.assertTrue(Path(identity['base']).samefile(selected))


if __name__ == '__main__':
    unittest.main()
