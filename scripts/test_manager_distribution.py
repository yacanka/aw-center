"""Full portable media includes its executable and cannot trust stale host paths."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.launcher.model import LauncherError
from scripts.manager.payload import prepare_source_payload
from scripts.test_launcher_bundle import project_at


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = project_at(self.root / 'project')
        self.media = self.root / 'media'
        prepare_source_payload(self.project, self.media / 'source')
        (self.media / '_internal').mkdir()
        (self.media / '_internal/python311.dll').write_bytes(b'embedded runtime fixture')
        (self.media / 'AWCenterManager.exe').write_bytes(b'manager fixture')

    def module(self):
        try:
            return importlib.import_module('scripts.manager.distribution')
        except ModuleNotFoundError:
            self.fail('Full Manager distribution support is missing')

    def test_complete_manifest_detects_missing_or_changed_executable(self):
        distribution = self.module()
        distribution.seal_distribution(self.media)
        distribution.verify_distribution(self.media)
        (self.media / 'AWCenterManager.exe').write_bytes(b'tampered')
        with self.assertRaises(LauncherError):
            distribution.verify_distribution(self.media)

    def test_startup_defaults_use_package_paths_but_preserve_explicit_root(self):
        distribution = self.module()
        (self.media / 'install-manifest.json').write_text('{}')
        distribution.seal_distribution(self.media, complete=True)
        from scripts.manager import paths
        old = {'source_root': 'Z:/old-machine/source', 'offline_dir': 'Z:/old-package', 'source_mode': 'online'}
        with patch.object(paths.sys, 'frozen', True, create=True), \
             patch.object(paths.sys, 'executable', str(self.media / 'AWCenterManager.exe')):
            actual = paths.startup_values(old, None)
            self.assertEqual(actual['source_root'], str(self.media / 'source'))
            self.assertEqual(actual['offline_dir'], str(self.media))
            self.assertEqual(actual['source_mode'], 'offline')
            explicit = self.root / 'operator-source'
            self.assertEqual(paths.startup_values(old, explicit)['source_root'], str(explicit))

    def test_distribution_copy_rejects_different_source(self):
        distribution = self.module()
        distribution.seal_distribution(self.media)
        other = self.root / 'other'
        prepare_source_payload(self.project, other / 'source')
        (other / 'source/launcher.py').write_text('different source')
        with self.assertRaises(LauncherError):
            distribution.copy_manager(self.media, other)
        self.assertFalse((other / 'AWCenterManager.exe').exists())
