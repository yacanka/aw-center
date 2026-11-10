"""Complete media must serve every supported CPython 3.11 patch release."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation_bundle as bundle
from scripts.launcher_test_support import create_project


class WheelPatchCompatibilityTests(unittest.TestCase):
    def test_download_and_offline_verification_both_use_the_union(self):
        from scripts.launcher.installation_sources import SourceSettings
        import subprocess
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            project.requirements.write_text('old-patch==2 ; python_full_version < "3.11.3"\n')
            original_capture = bundle._capture
            resolutions = []
            def capture(command, project, overrides, *, progress=None):
                if '-c' in command:
                    return original_capture(command, project, overrides)
                resolutions.append(Path(command[command.index('-r') + 1]).read_text())
                if '--wheel-dir' in command:
                    (Path(command[command.index('--wheel-dir') + 1]) / 'old_patch.whl').write_bytes(b'fixture')
                else:
                    self.assertIn('--no-index', command)
                return subprocess.CompletedProcess(command, 0, '', '')
            with patch.object(bundle, '_capture', side_effect=capture):
                bundle._acquire_wheels(project, root / 'wheels', SourceSettings(), {})
            self.assertEqual(resolutions, ['old-patch==2\n', 'old-patch==2\n'])

    def test_acquisition_includes_patch_conditional_pins_without_changing_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            original = (
                'always==1\n'
                'old-patch==2 ; python_full_version < "3.11.3"\n'
                'exact-patch==3 ; python_full_version == "3.11.7"\n'
                'future-patch==4 ; python_full_version > "3.11.40"\n'
                'wrong-platform==5 ; sys_platform == "not-a-platform"\n'
                'wrong-python==6 ; python_version == "3.12"\n'
            )
            project.requirements.write_text(original)
            output = root / 'acquisition.txt'
            bundle._patch_requirements(project, sys.executable, output, {})
            self.assertEqual(output.read_text().splitlines(),
                             ['always==1', 'old-patch==2', 'exact-patch==3', 'future-patch==4'])
            self.assertEqual(project.requirements.read_text(), original)

    def test_current_lock_keeps_async_timeout_for_early_311(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            lock = Path(__file__).resolve().parents[1] / 'requirements.txt'
            project.requirements.write_bytes(lock.read_bytes())
            output = root / 'acquisition.txt'
            bundle._patch_requirements(project, sys.executable, output, {})
            self.assertIn('async-timeout==5.0.1', output.read_text().splitlines())
            self.assertNotIn(' ; ', output.read_text())
