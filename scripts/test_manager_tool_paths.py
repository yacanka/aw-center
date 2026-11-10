"""Normalize selected tool paths without probing disks or interpreting commands."""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.manager.paths import normalize_task_paths


class ToolPathTests(unittest.TestCase):
    def setUp(self):
        self.base = Path.cwd() / 'worker'
        self.worker = patch('scripts.manager.paths.worker_directory', return_value=self.base)
        self.worker.start()
        self.addCleanup(self.worker.stop)

    def test_quoted_relative_node_file_and_directory_use_worker_base(self):
        for selection, expected in (
            ('"./tools/Node 24/node.exe"', self.base / 'tools' / 'Node 24' / 'node.exe'),
            ("'./tools/Node 24'", self.base / 'tools' / 'Node 24'),
        ):
            with self.subTest(selection=selection):
                values = normalize_task_paths({'node_command': selection})
                self.assertEqual(values['node_command'], str(expected))

    def test_python_and_node_paths_share_quote_and_relative_path_rules(self):
        values = normalize_task_paths({
            'python_command': "'./tools/Python 311/python.exe'",
            'node_command': "'./tools/Node 24/node.exe'",
        })
        self.assertEqual(values['python_command'], str(self.base / 'tools' / 'Python 311' / 'python.exe'))
        self.assertEqual(values['node_command'], str(self.base / 'tools' / 'Node 24' / 'node.exe'))

    def test_node_executable_names_remain_single_literal_selections(self):
        for selection, expected in (('node', 'node'), ('node.exe', 'node.exe'), ('"node"', 'node'),
                                    ('node --version', 'node --version'), ('node && echo unexpected', 'node && echo unexpected')):
            with self.subTest(selection=selection):
                self.assertEqual(normalize_task_paths({'node_command': selection})['node_command'], expected)

    def test_home_relative_node_path_uses_operator_environment(self):
        home = self.base.parent / 'operator'
        variable = 'USERPROFILE' if os.name == 'nt' else 'HOME'
        with patch.dict(os.environ, {variable: str(home)}):
            values = normalize_task_paths({'node_command': '"~/Node 24/node.exe"'})
        self.assertEqual(values['node_command'], str(home / 'Node 24' / 'node.exe'))

    def test_normalization_leaves_input_snapshot_unchanged_without_disk_checks(self):
        values = {'node_command': '"./Node 24/node.exe"'}
        with patch.object(Path, 'resolve', side_effect=AssertionError('No disk checks on Tk')):
            normalized = normalize_task_paths(values)
        self.assertEqual(normalized['node_command'], str(self.base / 'Node 24' / 'node.exe'))
        self.assertEqual(values, {'node_command': '"./Node 24/node.exe"'})
