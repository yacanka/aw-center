"""Regression tests for bounded launcher project discovery."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.launcher.discovery import bounded_matches, choose_file, choose_vue_manifest
from scripts.launcher.model import LauncherError


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write_manifest(self, relative: str, *, vue: bool = True) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        dependencies = {"vue": "^3.0.0"} if vue else {}
        path.write_text(json.dumps({"dependencies": dependencies}), encoding="utf-8")
        return path

    def test_preferred_frontend_manifest_avoids_recursive_discovery(self) -> None:
        preferred = self.write_manifest("frontend/package.json")
        self.write_manifest("other/package.json")
        with mock.patch("os.scandir", side_effect=AssertionError("unnecessary directory scan")):
            self.assertEqual(choose_vue_manifest(self.root), preferred)

    def test_root_vue_manifest_avoids_fallback_after_non_vue_frontend(self) -> None:
        self.write_manifest("frontend/package.json", vue=False)
        preferred = self.write_manifest("package.json")
        with mock.patch("os.scandir", side_effect=AssertionError("unnecessary directory scan")):
            self.assertEqual(choose_vue_manifest(self.root), preferred)

    def test_generated_trees_are_pruned_before_scanning(self) -> None:
        expected = self.write_manifest("client/package.json")
        forbidden = []
        for name in (".git", ".venv", "node_modules", "dist", "build"):
            generated = self.write_manifest(f"workspace/{name}/nested/package.json")
            forbidden.append(generated.parent.parent)
        original_scandir = os.scandir

        def scan(path):
            directory = Path(path)
            self.assertFalse(
                any(directory == ignored or ignored in directory.parents for ignored in forbidden),
                f"generated directory was traversed: {directory}",
            )
            return original_scandir(path)

        with mock.patch("os.scandir", side_effect=scan):
            self.assertEqual(bounded_matches(self.root, "package.json"), [expected])

    def test_depth_limit_is_applied_before_descending(self) -> None:
        expected = self.write_manifest("one/two/three/package.json")
        beyond_limit = self.write_manifest("one/two/three/four/five/package.json")
        forbidden = beyond_limit.parents[1]
        original_scandir = os.scandir

        def scan(path):
            directory = Path(path)
            self.assertFalse(
                directory == forbidden or forbidden in directory.parents,
                f"directory beyond discovery depth was traversed: {directory}",
            )
            return original_scandir(path)

        with mock.patch("os.scandir", side_effect=scan):
            self.assertEqual(bounded_matches(self.root, "package.json"), [expected])

    def test_fallback_preserves_sorted_selection_and_skips_non_vue_manifests(self) -> None:
        self.write_manifest("frontend/package.json", vue=False)
        self.write_manifest("package.json", vue=False)
        self.write_manifest("z-client/package.json")
        expected = self.write_manifest("b-client/package.json")
        self.write_manifest("a-tool/package.json", vue=False)
        self.assertEqual(choose_vue_manifest(self.root), expected)

    def test_vue_plugin_manifest_is_supported_in_fallback(self) -> None:
        manifest = self.root / "client/package.json"
        manifest.parent.mkdir()
        manifest.write_text(
            json.dumps({"devDependencies": {"@vitejs/plugin-vue": "^5.0.0"}}),
            encoding="utf-8",
        )
        self.assertEqual(choose_vue_manifest(self.root), manifest)

    def test_invalid_preferred_manifest_still_reports_manifest_error(self) -> None:
        manifest = self.write_manifest("frontend/package.json")
        manifest.write_text("{", encoding="utf-8")
        self.write_manifest("client/package.json")
        with self.assertRaisesRegex(LauncherError, "invalid package manifest"):
            choose_vue_manifest(self.root)

    def test_missing_vue_manifest_still_reports_discovery_error(self) -> None:
        self.write_manifest("client/package.json", vue=False)
        with self.assertRaisesRegex(LauncherError, "Vue package.json was not found"):
            choose_vue_manifest(self.root)

    def test_invalid_fallback_manifest_is_reported_even_after_vue_match(self) -> None:
        self.write_manifest("a-client/package.json")
        invalid = self.write_manifest("z-tool/package.json")
        invalid.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(LauncherError, "invalid package manifest"):
            choose_vue_manifest(self.root)

    def test_choose_file_retains_preferred_order(self) -> None:
        first = self.root / "manage.py"
        first.touch()
        (self.root / "backend").mkdir()
        (self.root / "backend/manage.py").touch()
        self.assertEqual(
            choose_file(self.root, "manage.py", preferred=("manage.py", "backend/manage.py")),
            first,
        )

    def test_choose_file_fallback_rejects_ambiguous_matches(self) -> None:
        for name in ("service-a", "service-b"):
            directory = self.root / name
            directory.mkdir()
            (directory / "manage.py").touch()
        with self.assertRaisesRegex(LauncherError, "multiple manage.py files found"):
            choose_file(self.root, "manage.py", preferred=("manage.py", "backend/manage.py"))

    def test_choose_file_fallback_selects_one_match(self) -> None:
        directory = self.root / "service"
        directory.mkdir()
        expected = directory / "manage.py"
        expected.touch()
        self.assertEqual(choose_file(self.root, "manage.py", preferred=()), expected)

    def test_choose_file_without_matches_retains_discovery_error(self) -> None:
        with self.assertRaisesRegex(LauncherError, "manage.py was not found"):
            choose_file(self.root, "manage.py", preferred=())
