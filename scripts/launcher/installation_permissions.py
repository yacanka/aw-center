"""Owner-only installation storage without localized ACL command parsing."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import stat

from .model import LauncherError


class PermissionCheckError(LauncherError):
    """An allowlisted check identifier and optional numeric Windows API error."""

    def __init__(self, permission_code, *, winerror=None):
        super().__init__('Owner-only storage permission verification failed')
        self.permission_code = permission_code
        self.winerror = winerror


def require_unlinked(path: Path) -> None:
    """Reject links and Windows reparse points in every existing ancestor."""
    path = Path(os.path.abspath(path))
    for ancestor in (*reversed(path.parents), path):
        try:
            information = ancestor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(information.st_mode) or getattr(information, 'st_file_attributes', 0) & 0x400:
            raise LauncherError('Installation paths must not contain symlinks or reparse points')


def require_local_ntfs(path: Path) -> None:
    """USB is transport media; mutable application state stays on local NTFS."""
    require_unlinked(path)
    if os.name != 'nt':
        return
    from ctypes import wintypes
    path = Path(path).absolute()
    for key in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer'):
        if os.environ.get(key) and path.is_relative_to(Path(os.environ[key]).absolute()):
            raise LauncherError('Çalışma dizini OneDrive dışında yerel NTFS üzerinde olmalı.')
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetVolumePathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumePathNameW.restype = wintypes.BOOL
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.GetDriveTypeW.restype = wintypes.UINT
    kernel.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumeInformationW.restype = wintypes.BOOL
    volume, filesystem = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(256)
    valid = kernel.GetVolumePathNameW(str(existing), volume, len(volume))
    valid = valid and kernel.GetDriveTypeW(volume.value) == 3
    valid = valid and kernel.GetVolumeInformationW(volume.value, None, 0, None, None, None, filesystem, len(filesystem))
    if not valid or filesystem.value.upper() != 'NTFS':
        raise LauncherError('Kurulum klasörünü USB/ağ sürücüsünden yerel NTFS diske kopyalayın.')


def secure_path(path: Path) -> None:
    """Set exactly current-owner access on a newly created file or directory."""
    require_unlinked(path)
    if os.name == 'nt':
        _windows_permissions(path, apply=True)
    else:
        if path.stat().st_uid != os.getuid():
            raise LauncherError('Installation storage belongs to a different user')
        path.chmod(0o700 if path.is_dir() else 0o600)
    require_private(path)


def require_private(path: Path) -> None:
    """Verify existing storage without silently repairing unsafe permissions."""
    require_unlinked(path)
    if os.name == 'nt':
        _windows_permissions(path, apply=False)
        return
    information = path.stat()
    if information.st_uid != os.getuid() or information.st_mode & 0o077:
        raise LauncherError('Installation storage must be owned by and accessible only to the current user')
    if not (stat.S_ISREG(information.st_mode) or stat.S_ISDIR(information.st_mode)):
        raise LauncherError('Installation storage must be a regular file or directory')


def _windows_permissions(path: Path, *, apply: bool) -> None:
    """Apply/verify a protected, single-ACE DACL and the process token owner SID."""
    from ctypes import wintypes

    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    pointer = ctypes.c_void_p
    dword = wintypes.DWORD
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, dword, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, pointer, dword, ctypes.POINTER(dword)]
    advapi.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, dword, ctypes.POINTER(pointer), ctypes.POINTER(dword)]
    advapi.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, dword, pointer]
    advapi.GetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, dword, ctypes.POINTER(pointer), ctypes.POINTER(pointer), ctypes.POINTER(pointer), ctypes.POINTER(pointer), ctypes.POINTER(pointer)]
    advapi.GetNamedSecurityInfoW.restype = dword
    advapi.EqualSid.argtypes = [pointer, pointer]
    advapi.GetSecurityDescriptorControl.argtypes = [pointer, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(dword)]
    advapi.GetAclInformation.argtypes = [pointer, pointer, dword, ctypes.c_int]
    advapi.GetAce.argtypes = [pointer, dword, ctypes.POINTER(pointer)]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer

    class AclSize(ctypes.Structure):
        _fields_ = [('count', dword), ('used', dword), ('free', dword)]

    class AccessAce(ctypes.Structure):
        _fields_ = [('kind', ctypes.c_ubyte), ('flags', ctypes.c_ubyte), ('size', wintypes.WORD), ('mask', dword), ('sid', dword)]

    token = wintypes.HANDLE()
    owned = []

    def checked(value, code, *, api=True):
        if not value:
            raise PermissionCheckError(code, winerror=ctypes.get_last_error() if api else None)
        return value

    try:
        checked(advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)), 'token_open')
        size = dword()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        checked(advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)), 'token_read')
        user_sid = ctypes.cast(buffer, ctypes.POINTER(pointer))[0]
        sid_text = wintypes.LPWSTR()
        checked(advapi.ConvertSidToStringSidW(user_sid, ctypes.byref(sid_text)), 'sid_read')
        owned.append(ctypes.cast(sid_text, pointer))
        if apply:
            descriptor = pointer()
            inheritance = 'OICI' if path.is_dir() else ''
            sddl = f'O:{sid_text.value}D:P(A;{inheritance};FA;;;{sid_text.value})'
            checked(advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None), 'acl_build')
            owned.append(descriptor)
            checked(advapi.SetFileSecurityW(str(path), 0x80000005, descriptor), 'acl_apply')
        owner, dacl, descriptor = pointer(), pointer(), pointer()
        status = advapi.GetNamedSecurityInfoW(str(path), 1, 5, ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(descriptor))
        if status:
            raise PermissionCheckError('acl_read', winerror=status)
        owned.append(descriptor)
        checked(owner and dacl and advapi.EqualSid(owner, user_sid), 'owner_mismatch', api=False)
        control, revision = wintypes.WORD(), dword()
        checked(advapi.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)), 'acl_control')
        checked(control.value & 0x1000, 'acl_inheritance', api=False)
        information = AclSize()
        checked(advapi.GetAclInformation(dacl, ctypes.byref(information), ctypes.sizeof(information), 2), 'acl_information')
        checked(information.count == 1, 'acl_entries', api=False)
        ace_pointer = pointer()
        checked(advapi.GetAce(dacl, 0, ctypes.byref(ace_pointer)), 'ace_read')
        ace = ctypes.cast(ace_pointer, ctypes.POINTER(AccessAce)).contents
        checked(ace.kind == 0 and ace.flags == (3 if path.is_dir() else 0) and ace.mask == 0x1f01ff, 'ace_permissions', api=False)
        checked(advapi.EqualSid(ace_pointer.value + AccessAce.sid.offset, user_sid), 'ace_owner', api=False)
    finally:
        for allocation in reversed(owned):
            kernel.LocalFree(allocation)
        if token:
            kernel.CloseHandle(token)
