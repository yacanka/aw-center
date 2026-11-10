"""Resource conflicts are distinct from independent desktop operations."""
import unittest
import os
from unittest.mock import patch
from pathlib import Path

from scripts.manager.task_policy import claims_for, conflicts
from scripts.manager import paths


class TaskPolicyTests(unittest.TestCase):
    def test_relative_target_and_worker_absolute_target_conflict(self):
        with patch('scripts.manager.paths.worker_directory', return_value=Path('/worker')):
            left = paths.normalize_task_paths({'output': 'bundle'})
            right = paths.normalize_task_paths({'output': '/worker/bundle'})
        self.assertEqual(left['output'], right['output'])
        self.assertTrue(self.conflict(('bundle', left), ('bundle', right)))

    def test_home_target_and_absolute_target_conflict(self):
        key = 'USERPROFILE' if os.name == 'nt' else 'HOME'
        with patch.dict(os.environ, {key: '/operator'}):
            left = paths.normalize_task_paths({'output': '~/bundle'})
            right = paths.normalize_task_paths({'output': '/operator/bundle'})
        self.assertEqual(left['output'], right['output'])

    def conflict(self, left, right):
        return conflicts(claims_for(*left), claims_for(*right))

    def test_running_dev_allows_diagnostics_source_probe_and_bundle(self):
        running = ('start', {'profile': 'dev', 'source_root': '/dev'})
        for action in ('doctor', 'test-sources', 'bundle'):
            with self.subTest(action=action):
                self.assertFalse(self.conflict(running, (action, {'profile': 'dev', 'source_root': '/dev', 'output': '/bundle'})))

    def test_same_profile_lifecycle_conflicts_even_for_different_release_paths(self):
        self.assertTrue(self.conflict(('start', {'profile': 'prod', 'source_root': '/release-a'}),
                                      ('start', {'profile': 'prod', 'source_root': '/release-b'})))

    def test_dev_and_prod_start_can_run_independently(self):
        self.assertFalse(self.conflict(('start', {'profile': 'dev', 'source_root': '/dev'}),
                                       ('start', {'profile': 'prod', 'source_root': '/prod'})))

    def test_provision_cannot_rewrite_a_running_source_or_shared_runtime(self):
        for source in ('/dev', '/other'):
            self.assertTrue(self.conflict(('start', {'profile': 'dev', 'source_root': '/dev'}),
                                          ('provision', {'profile': 'prod', 'source_root': source})))

    def test_two_bundle_targets_cannot_overlap(self):
        self.assertTrue(self.conflict(('bundle', {'source_root': '/src', 'output': '/out'}),
                                      ('bundle', {'source_root': '/src', 'output': '/out/child'})))
        self.assertFalse(self.conflict(('bundle', {'source_root': '/src', 'output': '/out-a'}),
                                       ('bundle', {'source_root': '/src', 'output': '/out-b'})))

    def test_duplicate_diagnostic_is_explicitly_conflicting_not_queued(self):
        self.assertTrue(self.conflict(('doctor', {'profile': 'dev'}), ('doctor', {'profile': 'dev'})))
        self.assertFalse(self.conflict(('doctor', {'profile': 'dev'}), ('doctor', {'profile': 'prod'})))


if __name__ == '__main__':
    unittest.main()
