"""Owner-only installation storage without localized ACL command parsing."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import stat

from .model import LauncherError


PERMISSION_CHECK_LABELS = {
    'path_open': 'Dosya / klasör izin denetimi için açılamadı',
    'path_information': 'Dosya / klasör türünü okuma',
    'path_reparse': 'Bağlantı / reparse noktası kurulum alanı olarak kullanılamaz',
    'path_links': 'Birden fazla hard link içeren dosyanın izinleri otomatik değiştirilemez',
    'path_type_changed': 'İzin kontrolü sırasında dosya / klasör türü değişti',
    'directory_type': 'Kurulum klasörü gereken yerde normal bir klasör bulunamadı',
    'path_scope': 'Klasör yönetilen kurulum alanının dışında',
    'path_identity': 'Açılan dosya / klasör beklenen kurulum yoluyla eşleşmiyor',
    'token_open': 'Windows işlem kimliğini açma', 'token_read': 'Windows işlem kimliğini okuma',
    'sid_read': 'Windows kullanıcı kimliğini okuma', 'acl_build': 'Özel izin tanımını oluşturma',
    'acl_apply': 'Özel erişim izinlerini uygulama', 'acl_read': 'Mevcut erişim izinlerini okuma',
    'owner_mismatch': 'Dosya / klasör sahibi mevcut kullanıcıyla eşleşmiyor',
    'acl_control': 'İzin kalıtım bilgisini okuma', 'acl_inheritance': 'Üst klasörden gelen izinler yalıtılmamış',
    'acl_information': 'Erişim listesi bilgisini okuma', 'acl_entries': 'Yalnız mevcut kullanıcıya ait tek izin kaydı bekleniyor',
    'ace_read': 'Erişim kaydını okuma', 'ace_permissions': 'Erişim kapsamı kullanıcıya özel değil',
    'ace_owner': 'Erişim kaydının sahibi mevcut kullanıcıyla eşleşmiyor',
}


class PermissionCheckError(LauncherError):
    """An allowlisted check identifier and optional numeric Windows API error."""

    def __init__(self, permission_code, *, winerror=None):
        self.permission_code = permission_code if permission_code in PERMISSION_CHECK_LABELS else 'permission_failed'
        self.code = 'storage_' + self.permission_code
        self.winerror = winerror if type(winerror) is int and winerror > 0 else None
        label = PERMISSION_CHECK_LABELS.get(self.permission_code, 'Sahiplik veya erişim izinleri doğrulanamadı')
        message = 'Özel kurulum alanı izin kontrolü: ' + label + '.'
        if self.winerror is not None:
            message += f' WinError: {self.winerror}.'
        self.remedy = ('Kurulumu oluşturan Windows hesabıyla açın. %LOCALAPPDATA%\\AWCenter sahiplik ve yalnız kullanıcıya açık izinlerini BT ile kontrol edin; mevcut profil veya veritabanını silmeyin.'
                       if self.permission_code in {'owner_mismatch', 'ace_owner'} else
                       'Kendi Windows hesabınızla açın. %LOCALAPPDATA%\\AWCenter erişimini, izin politikasını ve güvenlik yazılımının engellemesini BT ile kontrol edin; rapordaki izin ve sistem kodunu kullanın.')
        super().__init__(message)


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


def secure_path(path: Path, *, file_descriptor: int | None = None) -> None:
    """Set exactly current-owner access on a newly created file or directory."""
    require_unlinked(path)
    if os.name == 'nt':
        _windows_permissions(path, apply=True, file_descriptor=file_descriptor)
    else:
        if file_descriptor is not None and not os.path.samestat(os.fstat(file_descriptor), path.stat()):
            raise PermissionCheckError('path_identity')
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


def prepare_private(path: Path, *, file_descriptor: int | None = None) -> bool:
    """Tighten current-user inherited ACLs on managed directories/inert locks only.

    Never use this instead of require_private when reading persisted user data.
    Protected unexpected ACLs and ownership/API failures remain terminal.
    Returns whether Windows inheritance was repaired; POSIX checks stay strict.
    """
    require_unlinked(path)
    if os.name == 'nt':
        return _windows_permissions(path, apply=False, repair_inheritance=True,
                                    file_descriptor=file_descriptor)
    if file_descriptor is not None and not os.path.samestat(os.fstat(file_descriptor), path.stat()):
        raise PermissionCheckError('path_identity')
    require_private(path)
    return False


def _require_windows_handle_path(kernel, handle, path: Path) -> None:
    """Reject ancestor-junction substitution, allowing normal DOS long names."""
    from ctypes import wintypes
    kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel.GetLongPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetLongPathNameW.restype = wintypes.DWORD
    actual, expected = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(32768)
    actual_length = kernel.GetFinalPathNameByHandleW(handle, actual, len(actual), 0)
    expected_length = kernel.GetLongPathNameW(str(Path(os.path.abspath(path))), expected, len(expected))
    if not actual_length or not expected_length:
        raise PermissionCheckError('path_identity', winerror=ctypes.get_last_error())
    if actual_length >= len(actual) or expected_length >= len(expected):
        raise PermissionCheckError('path_identity')

    def normalized(value):
        if value.startswith('\\\\?\\UNC\\'):
            value = '\\\\' + value[8:]
        elif value.startswith('\\\\?\\'):
            value = value[4:]
        return os.path.normcase(os.path.normpath(value))

    if normalized(actual.value) != normalized(expected.value):
        raise PermissionCheckError('path_identity')


def _windows_permissions(path: Path, *, apply: bool, repair_inheritance: bool = False,
                         file_descriptor: int | None = None) -> bool:
    """Verify/secure the same non-reparse handle; recovery never changes owner."""
    from ctypes import wintypes

    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    pointer = ctypes.c_void_p
    dword = wintypes.DWORD
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, dword, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, pointer, dword, ctypes.POINTER(dword)]
    advapi.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, dword, ctypes.POINTER(pointer), ctypes.POINTER(dword)]
    advapi.GetSecurityDescriptorDacl.argtypes = [pointer, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(pointer), ctypes.POINTER(wintypes.BOOL)]
    advapi.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, dword, ctypes.POINTER(pointer), ctypes.POINTER(pointer), ctypes.POINTER(pointer), ctypes.POINTER(pointer), ctypes.POINTER(pointer)]
    advapi.GetSecurityInfo.restype = dword
    advapi.SetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, dword, pointer, pointer, pointer, pointer]
    advapi.SetSecurityInfo.restype = dword
    advapi.EqualSid.argtypes = [pointer, pointer]
    advapi.GetSecurityDescriptorControl.argtypes = [pointer, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(dword)]
    advapi.GetAclInformation.argtypes = [pointer, pointer, dword, ctypes.c_int]
    advapi.GetAce.argtypes = [pointer, dword, ctypes.POINTER(pointer)]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, dword, dword, pointer, dword, dword, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, pointer]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer

    class AclSize(ctypes.Structure):
        _fields_ = [('count', dword), ('used', dword), ('free', dword)]

    class AccessAce(ctypes.Structure):
        _fields_ = [('kind', ctypes.c_ubyte), ('flags', ctypes.c_ubyte), ('size', wintypes.WORD), ('mask', dword), ('sid', dword)]

    class FileInformation(ctypes.Structure):
        _fields_ = [('attributes', dword), ('created', wintypes.FILETIME),
                    ('accessed', wintypes.FILETIME), ('written', wintypes.FILETIME),
                    ('volume', dword), ('size_high', dword), ('size_low', dword),
                    ('links', dword), ('index_high', dword), ('index_low', dword)]

    token = wintypes.HANDLE()
    handle = None
    owned = []

    def checked(value, code, *, api=True):
        if not value:
            raise PermissionCheckError(code, winerror=ctypes.get_last_error() if api else None)
        return value

    def read_acl(*, initializing=False):
        owner, dacl, descriptor = pointer(), pointer(), pointer()
        status = advapi.GetSecurityInfo(handle, 1, 5, ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(descriptor))
        if status:
            raise PermissionCheckError('acl_read', winerror=status)
        owned.append(descriptor)
        checked(owner and dacl, 'owner_mismatch', api=False)
        owner_matches = advapi.EqualSid(owner, user_sid)
        if not owner_matches and initializing:
            # An elevated token may default newly created objects to its owner
            # group. Preserve initialization without authorizing foreign SIDs
            # or accepting that group during recovery/read-only verification.
            needed = dword()
            advapi.GetTokenInformation(token, 4, None, 0, ctypes.byref(needed))
            default_owner = ctypes.create_string_buffer(needed.value)
            checked(advapi.GetTokenInformation(token, 4, default_owner, needed, ctypes.byref(needed)), 'token_read')
            owner_matches = advapi.EqualSid(owner, ctypes.cast(default_owner, ctypes.POINTER(pointer))[0])
        checked(owner_matches, 'owner_mismatch', api=False)
        control, revision = wintypes.WORD(), dword()
        checked(advapi.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)), 'acl_control')
        return dacl, bool(control.value & 0x1000)

    def set_acl(*, include_owner):
        descriptor = pointer()
        inheritance = 'OICI' if directory else ''
        owner = f'O:{sid_text.value}' if include_owner else ''
        sddl = f'{owner}D:P(A;{inheritance};FA;;;{sid_text.value})'
        checked(advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None), 'acl_build')
        owned.append(descriptor)
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), pointer()
        checked(advapi.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)), 'acl_build')
        checked(present.value and dacl, 'acl_build', api=False)
        status = advapi.SetSecurityInfo(handle, 1, 0x80000005 if include_owner else 0x80000004,
                                       user_sid if include_owner else None, None, dacl, None)
        if status:
            raise PermissionCheckError('acl_apply', winerror=status)

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
        directory = path.is_dir()
        # MAXIMUM_ALLOWED on directories prevents SetSecurityInfo propagating
        # ACL changes to existing children. Files have no children and use exact
        # rights so open lock streams need not share DELETE access.
        # https://learn.microsoft.com/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo
        access = 0x20000 | (0x40000 if apply or repair_inheritance else 0) | (0x80000 if apply else 0)
        if directory and (apply or repair_inheritance):
            access = 0x02000000
        handle = kernel.CreateFileW(str(path), access, 7, None, 3, 0x02200000, None)
        checked(handle not in (None, pointer(-1).value), 'path_open')
        file_information = FileInformation()
        checked(kernel.GetFileInformationByHandle(handle, ctypes.byref(file_information)), 'path_information')
        checked(not file_information.attributes & 0x400, 'path_reparse', api=False)
        checked(directory == bool(file_information.attributes & 0x10), 'path_type_changed', api=False)
        if file_descriptor is not None:
            import msvcrt
            original = FileInformation()
            checked(kernel.GetFileInformationByHandle(msvcrt.get_osfhandle(file_descriptor), ctypes.byref(original)), 'path_information')
            checked((original.volume, original.index_high, original.index_low) ==
                    (file_information.volume, file_information.index_high, file_information.index_low),
                    'path_identity', api=False)
        dacl, protected = read_acl(initializing=apply)
        if apply:
            checked(directory or file_information.links == 1, 'path_links', api=False)
            _require_windows_handle_path(kernel, handle, path)
            set_acl(include_owner=True)
            dacl, protected = read_acl()
        repaired = repair_inheritance and not protected
        if repaired:
            checked(directory or file_information.links == 1, 'path_links', api=False)
            _require_windows_handle_path(kernel, handle, path)
            set_acl(include_owner=False)
            dacl, protected = read_acl()
        checked(protected, 'acl_inheritance', api=False)
        information = AclSize()
        checked(advapi.GetAclInformation(dacl, ctypes.byref(information), ctypes.sizeof(information), 2), 'acl_information')
        checked(information.count == 1, 'acl_entries', api=False)
        ace_pointer = pointer()
        checked(advapi.GetAce(dacl, 0, ctypes.byref(ace_pointer)), 'ace_read')
        ace = ctypes.cast(ace_pointer, ctypes.POINTER(AccessAce)).contents
        checked(ace.kind == 0 and ace.flags == (3 if directory else 0) and ace.mask == 0x1f01ff, 'ace_permissions', api=False)
        checked(advapi.EqualSid(ace_pointer.value + AccessAce.sid.offset, user_sid), 'ace_owner', api=False)
        return repaired
    finally:
        for allocation in reversed(owned):
            kernel.LocalFree(allocation)
        if handle not in (None, pointer(-1).value):
            kernel.CloseHandle(handle)
        if token:
            kernel.CloseHandle(token)
