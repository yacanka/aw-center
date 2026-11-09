"""Windows permission diagnostics retain error codes without exposing paths/SIDs."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import tempfile
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
            'GetAclInformation', 'GetAce', 'GetSecurityInfo', 'SetSecurityInfo',
            'GetSecurityDescriptorDacl')})
        api.OpenProcessToken.return_value = 0
        kernel = SimpleNamespace(GetCurrentProcess=Mock(return_value=1), CloseHandle=Mock(),
                                 LocalFree=Mock(), CreateFileW=Mock(), GetFileInformationByHandle=Mock(),
                                 GetFinalPathNameByHandleW=Mock(), GetLongPathNameW=Mock())
        with patch.object(ctypes, 'WinDLL', side_effect=[api, kernel], create=True), \
             patch.object(ctypes, 'get_last_error', return_value=5, create=True):
            with self.assertRaises(permissions.PermissionCheckError) as caught:
                permissions._windows_permissions(Path('unused-private-path'), apply=False)
        self.assertEqual(caught.exception.winerror, 5)
        self.assertEqual(caught.exception.permission_code, 'token_open')
        self.assertNotIn('unused-private-path', str(caught.exception))


class FileInformation(ctypes.Structure):
    _fields_ = [('attributes', wintypes.DWORD), ('created', wintypes.FILETIME),
                ('accessed', wintypes.FILETIME), ('written', wintypes.FILETIME),
                ('volume', wintypes.DWORD), ('size_high', wintypes.DWORD),
                ('size_low', wintypes.DWORD), ('links', wintypes.DWORD),
                ('index_high', wintypes.DWORD), ('index_low', wintypes.DWORD)]


class AccessAce(ctypes.Structure):
    _fields_ = [('kind', ctypes.c_ubyte), ('flags', ctypes.c_ubyte),
                ('size', wintypes.WORD), ('mask', wintypes.DWORD), ('sid', wintypes.DWORD)]


class WindowsAcl:
    """Win32 boundary double; the permission policy and ctypes buffers stay real."""

    def __init__(self, *, directory=True, protected=False):
        self.protected = protected
        self.owner_matches = True
        self.ace_owner_matches = True
        self.ace_count = 1
        self.attributes = 0x10 if directory else 0x80
        self.links = 1
        self.apply_error = 0
        self.apply_effective = True
        self.final_path = None
        self.substituted_identity = False
        self.sid = ctypes.create_string_buffer(16)
        self.sid_address = ctypes.addressof(self.sid)
        self.default_owner_address = self.sid_address
        self.sid_text = 'S-1-5-21-111-222-333-1001'
        self.ace = AccessAce(0, 3 if directory else 0, ctypes.sizeof(AccessAce), 0x1f01ff, 0)
        self.api = SimpleNamespace(**{name: Mock(side_effect=method) for name, method in (
            ('OpenProcessToken', self.open_token), ('GetTokenInformation', self.token_information),
            ('ConvertSidToStringSidW', self.sid_to_string),
            ('ConvertStringSecurityDescriptorToSecurityDescriptorW', self.build_descriptor),
            ('GetSecurityDescriptorDacl', self.descriptor_dacl),
            ('GetSecurityInfo', self.security_information), ('SetSecurityInfo', self.set_security),
            ('GetSecurityDescriptorControl', self.descriptor_control),
            ('EqualSid', self.equal_sid), ('GetAclInformation', self.acl_information),
            ('GetAce', self.get_ace))})
        self.kernel = SimpleNamespace(GetCurrentProcess=Mock(return_value=1),
            CreateFileW=Mock(return_value=77), GetFileInformationByHandle=Mock(side_effect=self.file_information),
            GetFinalPathNameByHandleW=Mock(side_effect=self.final_path_name),
            GetLongPathNameW=Mock(side_effect=self.long_path_name),
            CloseHandle=Mock(return_value=1), LocalFree=Mock(return_value=None))

    def open_token(self, process, access, token):
        token._obj.value = 7
        return 1

    def token_information(self, token, kind, buffer, size, needed):
        needed._obj.value = ctypes.sizeof(ctypes.c_void_p)
        if buffer is None:
            return 0
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0] = (
            self.default_owner_address if kind == 4 else self.sid_address)
        return 1

    def sid_to_string(self, sid, text):
        text._obj.value = self.sid_text
        return 1

    def build_descriptor(self, sddl, revision, descriptor, size):
        descriptor._obj.value = 400
        return 1

    def descriptor_dacl(self, descriptor, present, dacl, defaulted):
        present._obj.value = 1
        dacl._obj.value = 300
        defaulted._obj.value = 0
        return 1

    def file_information(self, handle, information):
        result = ctypes.cast(information, ctypes.POINTER(FileInformation)).contents
        result.attributes, result.links = self.attributes, self.links
        result.volume, result.index_high = 1, 0
        result.index_low = 2 if self.substituted_identity and handle == 77 else 1
        return 1

    def final_path_name(self, handle, buffer, size, flags):
        buffer.value = self.final_path or self.kernel.CreateFileW.call_args.args[0]
        return len(buffer.value)

    def long_path_name(self, path, buffer, size):
        buffer.value = path
        return len(buffer.value)

    def security_information(self, handle, kind, fields, owner, group, dacl, sacl, descriptor):
        owner._obj.value = self.sid_address if self.owner_matches else 999
        dacl._obj.value = 200
        descriptor._obj.value = 500
        return 0

    def set_security(self, handle, kind, fields, owner, group, dacl, sacl):
        if not self.apply_error and self.apply_effective:
            self.protected, self.ace_count = True, 1
            self.ace.flags = 3 if self.attributes & 0x10 else 0
            self.ace.mask = 0x1f01ff
            if fields & 1:
                self.owner_matches = True
        return self.apply_error

    def descriptor_control(self, descriptor, control, revision):
        control._obj.value = 0x1000 if self.protected else 0
        revision._obj.value = 1
        return 1

    def equal_sid(self, first, second):
        value = getattr(first, 'value', first)
        if value == ctypes.addressof(self.ace) + AccessAce.sid.offset:
            return self.ace_owner_matches
        return value == getattr(second, 'value', second)

    def acl_information(self, dacl, information, size, kind):
        ctypes.cast(information, ctypes.POINTER(wintypes.DWORD))[0] = self.ace_count
        return 1

    def get_ace(self, dacl, index, ace):
        ace._obj.value = ctypes.addressof(self.ace)
        return 1


class InheritedPermissionRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve()
        self.native = WindowsAcl()
        for patched in (
            patch.object(permissions, 'os', SimpleNamespace(name='nt', path=os.path)),
            patch.object(ctypes, 'WinDLL', side_effect=lambda name, **_: (
                self.native.api if name == 'advapi32' else self.native.kernel), create=True),
            patch.object(ctypes, 'get_last_error', return_value=5, create=True),
        ):
            patched.start()
            self.addCleanup(patched.stop)

    def test_startup_tightens_inherited_directory_acl_without_taking_ownership(self):
        self.assertTrue(permissions.prepare_private(self.path))
        permissions.require_private(self.path)
        self.assertEqual(self.native.api.SetSecurityInfo.call_count, 1)
        arguments = self.native.api.SetSecurityInfo.call_args.args
        self.assertEqual(arguments[:3], (77, 1, 0x80000004))
        self.assertIsNone(arguments[3])
        self.assertEqual(self.native.api.ConvertStringSecurityDescriptorToSecurityDescriptorW.call_args.args[0],
                         'D:P(A;OICI;FA;;;S-1-5-21-111-222-333-1001)')
        self.assertFalse(permissions.prepare_private(self.path))

    def test_inherited_lock_file_becomes_private_without_changing_its_contents(self):
        self.native = WindowsAcl(directory=False)
        path = self.path / 'installation.lock'
        path.write_bytes(b'keep-lock-byte')
        self.assertTrue(permissions.prepare_private(path))
        self.assertEqual(path.read_bytes(), b'keep-lock-byte')
        permissions.require_private(path)
        self.assertEqual(self.native.api.ConvertStringSecurityDescriptorToSecurityDescriptorW.call_args.args[0],
                         'D:P(A;;FA;;;S-1-5-21-111-222-333-1001)')

    def test_existing_inherited_lock_can_be_claimed_without_truncation(self):
        from scripts.launcher.resource_locks import _Lease
        self.native = WindowsAcl(directory=False)
        path = self.path / 'existing.lock'
        path.write_bytes(b'keep-lock-byte')
        with patch.object(_Lease, '_lock'), \
             patch.dict('sys.modules', {'msvcrt': SimpleNamespace(get_osfhandle=lambda fd: 88)}):
            lease = _Lease(path, True)
        try:
            self.assertTrue(self.native.protected)
            self.assertFalse(any(call.args[2] & 1 for call in self.native.api.SetSecurityInfo.call_args_list))
        finally:
            lease.close()
        self.assertEqual(path.read_bytes(), b'keep-lock-byte')

    def test_existing_protected_lock_does_not_reset_ownership(self):
        from scripts.launcher.resource_locks import _Lease
        self.native = WindowsAcl(directory=False, protected=True)
        path = self.path / 'protected.lock'
        path.write_bytes(b'keep')
        with patch.object(_Lease, '_lock'), \
             patch.dict('sys.modules', {'msvcrt': SimpleNamespace(get_osfhandle=lambda fd: 88)}):
            lease = _Lease(path, True)
        lease.close()
        self.native.api.SetSecurityInfo.assert_not_called()
        self.assertEqual(path.read_bytes(), b'keep')

    def test_directory_repair_does_not_propagate_acls_into_existing_contents(self):
        permissions.prepare_private(self.path)
        # SetSecurityInfo's documented MAXIMUM_ALLOWED mode suppresses child
        # propagation. Ordinary lock-file handles instead request exact rights.
        self.assertEqual(self.native.kernel.CreateFileW.call_args.args[1], 0x02000000)

    def test_profile_preparation_uses_the_same_inherited_directory_recovery(self):
        from scripts.launcher.installation_profiles import _create_private_directory
        _create_private_directory(self.path)
        self.assertTrue(self.native.protected)
        permissions.require_private(self.path)

    def test_existing_inherited_intermediate_is_prepared_inside_the_known_root(self):
        from scripts.launcher import installation_state as state
        parent = self.path / 'cache'
        parent.mkdir()
        leaf = parent / 'packages' / 'python'
        # Emulate inheritance left on the existing intermediate only; other
        # paths have already passed the full native-boundary tests above.
        inherited = {parent}
        def native(path, *, apply, repair_inheritance=False, file_descriptor=None):
            if path in inherited:
                if not (apply or repair_inheritance):
                    raise permissions.PermissionCheckError('acl_inheritance')
                inherited.remove(path)
                return True
            return False
        with patch.object(permissions, '_windows_permissions', side_effect=native):
            state.private_directory(leaf, root=self.path)
            permissions.require_private(parent)
        self.assertEqual(inherited, set())

    def test_secure_path_rejects_foreign_owner_before_writing_permissions(self):
        self.native.owner_matches = False
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.secure_path(self.path)
        self.assertEqual(caught.exception.code, 'storage_owner_mismatch')
        self.native.api.SetSecurityInfo.assert_not_called()

    def test_secure_path_rejects_hard_link_before_writing_permissions(self):
        self.native = WindowsAcl(directory=False, protected=True)
        self.native.links = 2
        path = self.path / 'linked'
        path.touch()
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.secure_path(path)
        self.assertEqual(caught.exception.code, 'storage_path_links')
        self.native.api.SetSecurityInfo.assert_not_called()

    def test_ancestor_substitution_cannot_redirect_acl_repair(self):
        self.native.final_path = str(self.path.parent / 'another-owner-directory' / 'same-user-leaf')
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.prepare_private(self.path)
        self.assertEqual(caught.exception.code, 'storage_path_identity')
        self.native.api.SetSecurityInfo.assert_not_called()

    def test_created_lock_identity_must_match_the_opened_permission_handle(self):
        self.native = WindowsAcl(directory=False)
        self.native.substituted_identity = True
        path = self.path / 'lock'
        path.touch()
        with patch.dict('sys.modules', {'msvcrt': SimpleNamespace(get_osfhandle=lambda fd: 88)}):
            with self.assertRaises(permissions.PermissionCheckError) as caught:
                permissions.secure_path(path, file_descriptor=12)
        self.assertEqual(caught.exception.code, 'storage_path_identity')
        self.native.api.SetSecurityInfo.assert_not_called()

    def test_new_object_can_use_the_process_default_owner_without_repairing_other_owners(self):
        # Elevated Windows tokens can default new objects to their owner group.
        self.native.owner_matches = False
        self.native.default_owner_address = 999
        permissions.secure_path(self.path)
        permissions.require_private(self.path)

    def test_read_only_permission_check_never_repairs_inheritance(self):
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.require_private(self.path)
        self.assertEqual(caught.exception.code, 'storage_acl_inheritance')
        self.native.api.SetSecurityInfo.assert_not_called()
        self.assertEqual(self.native.kernel.CreateFileW.call_args.args[1], 0x20000)

    def test_foreign_owner_is_rejected_before_any_acl_write(self):
        self.native.owner_matches = False
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.prepare_private(self.path)
        self.assertEqual(caught.exception.code, 'storage_owner_mismatch')
        self.native.api.SetSecurityInfo.assert_not_called()

    def test_protected_unexpected_acl_is_not_automatically_replaced(self):
        self.native.protected, self.native.ace_count = True, 2
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.prepare_private(self.path)
        self.assertEqual(caught.exception.code, 'storage_acl_entries')
        self.native.api.SetSecurityInfo.assert_not_called()

    def test_reparse_target_substituted_after_path_check_is_rejected(self):
        self.native.attributes |= 0x400
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.prepare_private(self.path)
        self.assertEqual(caught.exception.code, 'storage_path_reparse')
        self.native.api.SetSecurityInfo.assert_not_called()

    def test_inherited_hard_link_cannot_change_another_files_permissions(self):
        self.native = WindowsAcl(directory=False)
        self.native.links = 2
        path = self.path / 'linked.lock'
        path.touch()
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.prepare_private(path)
        self.assertEqual(caught.exception.code, 'storage_path_links')
        self.native.api.SetSecurityInfo.assert_not_called()

    def test_windows_rejection_retains_error_code_and_closes_file_handle(self):
        self.native.apply_error = 5
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.prepare_private(self.path)
        self.assertEqual(caught.exception.code, 'storage_acl_apply')
        self.assertEqual(caught.exception.winerror, 5)
        self.assertNotIn(str(self.path), str(caught.exception))
        self.assertIn(77, [getattr(call.args[0], 'value', call.args[0])
                           for call in self.native.kernel.CloseHandle.call_args_list])

    def test_ineffective_repair_is_verified_and_not_retried_forever(self):
        self.native.apply_effective = False
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            permissions.prepare_private(self.path)
        self.assertEqual(caught.exception.code, 'storage_acl_inheritance')
        self.assertEqual(self.native.api.SetSecurityInfo.call_count, 1)


class PrivateStorageTests(unittest.TestCase):
    def setUp(self):
        from scripts.launcher import installation_state
        self.state = installation_state
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / 'AWCenter'

    def test_every_new_ancestor_is_private_after_nested_directory_creation(self):
        path = self.home / 'cache' / 'packages' / 'python'
        self.state.private_directory(path)
        for item in (self.home, self.home / 'cache', self.home / 'cache/packages', path):
            permissions.require_private(item)

    def test_existing_private_file_is_not_accepted_as_a_directory(self):
        self.home.write_bytes(b'keep')
        permissions.secure_path(self.home)
        with self.assertRaises(permissions.PermissionCheckError) as caught:
            self.state.private_directory(self.home)
        self.assertEqual(caught.exception.code, 'storage_directory_type')
        self.assertEqual(self.home.read_bytes(), b'keep')

    def test_concurrent_directory_creation_is_revalidated_and_reused(self):
        mkdir = Path.mkdir
        def another_creator(path, *args, **kwargs):
            mkdir(path, mode=0o700)
            permissions.secure_path(path)
            raise FileExistsError('concurrent creator')
        with patch.object(Path, 'mkdir', another_creator):
            self.assertEqual(self.state.private_directory(self.home), self.home)
        permissions.require_private(self.home)

    def test_file_created_by_a_racing_process_is_not_reused_as_directory(self):
        def another_creator(path, *args, **kwargs):
            path.write_bytes(b'keep')
            permissions.secure_path(path)
            raise FileExistsError('concurrent creator')
        with patch.object(Path, 'mkdir', another_creator):
            with self.assertRaises(permissions.PermissionCheckError) as caught:
                self.state.private_directory(self.home)
        self.assertEqual(caught.exception.code, 'storage_directory_type')
        self.assertEqual(self.home.read_bytes(), b'keep')

    @unittest.skipIf(os.name == 'nt', 'POSIX existing-ancestor fixture')
    def test_unsafe_existing_intermediate_is_rejected_before_creating_descendants(self):
        self.state.private_directory(self.home)
        parent = self.home / 'cache'
        parent.mkdir(mode=0o755)
        with self.assertRaises(permissions.LauncherError):
            self.state.private_directory(parent / 'packages/python', root=self.home)
        self.assertFalse((parent / 'packages').exists())
        self.assertEqual(parent.stat().st_mode & 0o777, 0o755)

    def test_directory_boundary_rejects_escape_without_modifying_external_storage(self):
        outside = self.root / 'outside'
        with self.assertRaises(permissions.LauncherError):
            self.state.private_directory(self.home / '../outside', root=self.home)
        self.assertFalse(outside.exists())
        self.assertFalse(self.home.exists())

    def test_storage_preflight_leaves_existing_content_and_no_probe_files(self):
        config = self.state.private_directory(self.home / 'config')
        path = config / 'keep.env'
        path.write_bytes(b'fixture-content')
        permissions.secure_path(path)
        before = sorted(item.relative_to(self.home) for item in self.home.rglob('*'))
        messages = []
        self.state.prepare_installation_storage(self.home, progress=messages.append)
        self.assertEqual(path.read_bytes(), b'fixture-content')
        self.assertEqual(sorted(item.relative_to(self.home) for item in self.home.rglob('*')), before)
        self.assertNotIn(str(self.home), ' '.join(messages))

    def test_failed_atomic_write_probe_is_reported_and_cleans_its_scratch_directory(self):
        self.state.private_directory(self.home)
        error = PermissionError('private path and OS message')
        with patch.object(self.state.os, 'replace', side_effect=error):
            with self.assertRaises(PermissionError):
                self.state.prepare_installation_storage(self.home)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_cancelled_preflight_does_not_create_installation_storage(self):
        from scripts.launcher.process import OperationCancelled
        def cancelled(_):
            raise OperationCancelled()
        with self.assertRaises(OperationCancelled):
            self.state.prepare_installation_storage(self.home, progress=cancelled)
        self.assertFalse(self.home.exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX permission fixture')
    def test_preflight_never_repairs_persisted_environment_permissions(self):
        config = self.state.private_directory(self.home / 'config')
        path = config / 'dev.env'
        path.write_bytes(b'fixture-content')
        path.chmod(0o644)
        self.state.prepare_installation_storage(self.home)
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        with self.assertRaises(permissions.LauncherError):
            permissions.require_private(path)
