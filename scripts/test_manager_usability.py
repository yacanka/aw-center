"""The main opening action stays available after lightweight inspection."""
import unittest
import threading
from unittest.mock import patch

from scripts.launcher.installation_env import EnvironmentImportError
from scripts.manager import operations
from scripts.manager.view_model import ManagerTaskStates


class UsabilityTests(unittest.TestCase):
    def test_registered_unverified_profile_can_be_opened_without_a_diagnostic_step(self):
        states = ManagerTaskStates()
        states.handle_event({'type': 'profile', 'profile': 'dev', 'status': 'unverified',
                             'detail': 'Profil kayıtlı.'})

        presentation = states.profile_presentation('dev')

        self.assertEqual(presentation['action'], 'ensure')
        self.assertEqual(presentation['label'], 'AW Center’ı aç')
        self.assertEqual(presentation['url'], '')
        self.assertEqual(presentation['detail'], 'Profil kayıtlı.')

    def test_environment_error_shows_the_setting_remedy_and_correct_field(self):
        error = EnvironmentImportError('env_managed_setting_conflict', keys=('DATABASE_URL',))
        events = []

        with patch.object(operations, '_dispatch', side_effect=error):
            operations.execute({'action': 'ensure'}, events.append, lambda: None, threading.Event())

        failure = next(event for event in events if event['type'] == 'error')
        self.assertEqual(failure['code'], 'env_managed_setting_conflict')
        self.assertEqual(failure['field'], 'env_file')
        self.assertIn('DATABASE_URL', failure['message'])
        self.assertEqual(failure['remedy'], error.remedy)
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})
