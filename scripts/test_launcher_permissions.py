"""Windows permission diagnostics retain error codes without exposing paths/SIDs."""
import ctypes
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.launcher import installation_permissions as permissions


class PermissionDiagnosticsTests(unittest.TestCase):
    def test_native_api_failure_keeps_numeric_windows_error(self):
        api = SimpleNamespace(**{name: Mock() for name in (
            'OpenProcessToken', 'GetTokenInformation', 'ConvertSidToStringSidW',
            'ConvertStringSecurityDescriptorToSecurityDescriptorW', 'SetFileSecurityW',
            'GetNamedSecurityInfoW', 'EqualSid', 'GetSecurityDescriptorControl',
            'GetAclInformation', 'GetAce')})
        api.OpenProcessToken.return_value = 0
        kernel = SimpleNamespace(GetCurrentProcess=Mock(return_value=1), CloseHandle=Mock(), LocalFree=Mock())
        with patch.object(ctypes, 'WinDLL', side_effect=[api, kernel], create=True), \
             patch.object(ctypes, 'get_last_error', return_value=5, create=True):
            with self.assertRaises(permissions.PermissionCheckError) as caught:
                permissions._windows_permissions(Path('unused-private-path'), apply=False)
        self.assertEqual(caught.exception.winerror, 5)
        self.assertEqual(caught.exception.permission_code, 'token_open')
        self.assertNotIn('unused-private-path', str(caught.exception))
