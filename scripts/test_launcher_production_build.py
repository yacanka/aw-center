"""Manager production builds must survive older immutable source and missing lazy chunks."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.launcher import installation
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project


class ProductionBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name).resolve()
        self.project = create_project(root)
        self.profile = {"name": "prod", "installation_home": str(root / "home")}
        (root / "manager-source-manifest.json").write_text("verified old release fixture")
        self.node = root / "node.exe"
        self.npm = root / "npm/bin/npm-cli.js"
        self.npm.parent.mkdir(parents=True)
        self.node.write_bytes(b"node")
        self.npm.write_bytes(b"npm")
        self.npm_package = self.npm.parent.parent / "package.json"
        self.npm_package.write_text('{"version":"1"}')
        self.tools = {"AWCENTER_MANAGED_NODE": str(self.node), "AWCENTER_MANAGED_NPM_CLI": str(self.npm)}
        self.dist = self.project.frontend / "dist"
        self.lazy = self.dist / "assets/lazy.js"
        self.build = Mock(side_effect=self.make_output)
        self.deploy = Mock()
        self.report = Mock()

    def make_output(self):
        self.lazy.parent.mkdir(parents=True)
        self.lazy.write_bytes(b"lazy chunk")
        (self.dist / "index.html").write_bytes(b"shell")

    def prepare(self):
        from scripts.launcher.production_build import prepare_build
        prepare_build(self.project, self.profile, self.tools, self.build, self.deploy, self.report)

    def test_old_probe_without_field_rebuilds_missing_dist_or_missing_legacy_receipt(self):
        state = {"schema": "ready", "admin_exists": True}
        with patch.object(installation, "inspect_profile", side_effect=lambda *_: []), \
             patch.object(installation, "dependency_checks", return_value=[{"status": "ready"}]), \
             patch.object(installation, "backend_inspection", return_value=state):
            for existing in (False, True):
                if existing:
                    self.make_output()
                checks = installation._core_checks(self.project, self.profile, managed_build=True)
                self.assertIn(("frontend-build", "missing"), [(r.get("name"), r["status"]) for r in checks])
        self.prepare()
        backups = list((self.project.root / ".runtime/frontend-build-backups").glob("*/dist/assets/lazy.js"))
        self.assertEqual(len(backups), 1)
        self.prepare()
        self.build.assert_called_once()
        self.assertEqual(self.deploy.call_count, 2)

    def test_missing_lazy_chunk_rebuilds_even_when_entry_and_other_gates_stay_ready(self):
        self.prepare()
        self.lazy.unlink()
        with patch("scripts.launcher.toolchain._environment", return_value=self.tools), \
             patch.object(installation, "inspect_profile", return_value=[]), \
             patch.object(installation, "dependency_checks", return_value=[{"status": "ready"}]), \
             patch.object(installation, "backend_inspection", return_value={
                 "schema": "ready", "admin_exists": True, "frontend_build_ready": True}):
            checks = installation._core_checks(self.project, self.profile, managed_build=True)
        self.assertIn(("frontend-build", "missing"), [(r.get("name"), r["status"]) for r in checks])
        self.prepare()
        self.assertEqual(self.build.call_count, 2)
        self.assertTrue(self.lazy.is_file())

    def test_source_tool_or_vite_input_changes_invalidate_the_verified_build(self):
        self.prepare()
        for path in (self.project.root / "manager-source-manifest.json", self.node, self.npm_package):
            path.write_bytes(b"changed")
            self.prepare()
        with patch.dict(os.environ, {"VITE_APP_TITLE": "other title"}):
            self.prepare()
        self.assertEqual(self.build.call_count, 5)

    def test_failed_deployment_cannot_publish_a_success_receipt(self):
        self.deploy.side_effect = LauncherError("failed verification")
        with self.assertRaises(LauncherError):
            self.prepare()
        self.deploy.side_effect = None
        self.prepare()
        self.assertEqual(self.build.call_count, 2)

    def test_invalid_receipt_blocks_build_without_replacing_existing_output(self):
        from scripts.launcher.production_build import FrontendBuildError, _receipt
        self.prepare()
        path = _receipt(self.project)
        path.write_text('{"version":')
        with self.assertRaises(FrontendBuildError):
            self.prepare()
        self.assertEqual(path.read_text(), '{"version":')
        self.assertEqual(self.lazy.read_bytes(), b"lazy chunk")
        self.build.assert_called_once()

    def test_receipt_write_failure_keeps_previous_evidence_and_both_builds(self):
        from scripts.launcher import production_build
        self.prepare()
        receipt = production_build._receipt(self.project)
        previous = receipt.read_bytes()
        with patch.dict(os.environ, {"VITE_APP_TITLE": "updated"}), \
             patch.object(production_build.os, "fsync", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                self.prepare()
            self.assertFalse(production_build.build_is_current(self.project, self.profile, self.tools))
        self.assertEqual(receipt.read_bytes(), previous)
        self.assertEqual(list(receipt.parent.iterdir()), [receipt])
        self.assertTrue(self.lazy.is_file())
        self.assertEqual(len(list((self.project.root / ".runtime/frontend-build-backups").glob("*/dist/assets/lazy.js"))), 1)

    def test_inspection_reconstructs_the_same_selected_system_tools_as_build(self):
        from scripts.launcher import production_build
        self.profile['node_executable'] = str(self.node)
        with patch("scripts.launcher.system_node.find_npm_cli", return_value=self.npm):
            self.prepare()
            self.assertTrue(production_build.build_is_current(self.project, self.profile))
            self.assertFalse(production_build.build_is_current(self.project, self.profile, {
                **self.tools, 'VITE_APP_TITLE': 'overridden in build environment'}))
            self.npm_package.write_text('{"version":"2"}')
            self.assertFalse(production_build.build_is_current(self.project, self.profile))

    @unittest.skipIf(os.name == "nt", "Creating symlinks can require Windows privileges")
    def test_unsafe_output_path_is_preserved_without_invoking_npm(self):
        self.make_output()
        alias = self.dist / "alias"
        alias.symlink_to(self.project.package_json)
        with self.assertRaises(LauncherError):
            self.prepare()
        self.build.assert_not_called()
        self.assertTrue(alias.is_symlink())
