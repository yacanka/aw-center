"""Nonblocking, OS-owned profile/source/runtime leases shared by GUI and CLI."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import errno
import hashlib
import os
from pathlib import Path

from .installation_permissions import require_private, require_unlinked, secure_path
from .installation_state import private_directory
from .model import LauncherError

_held = ContextVar('awcenter_resource_leases', default=None)


class ResourceLockError(LauncherError):
    """A lock conflict or storage failure with no path/OS message disclosure."""

    def __init__(self, *, busy=False, system_error):
        self.code = 'resource_busy' if busy else 'storage_lock_failed'
        message = ('Başka bir işlem aynı profil veya kaynakları kullanıyor; işlem başlatılmadı.' if busy else
                   'Özel kurulum işlem kilidi alanına erişilemedi veya kilit oluşturulamadı.')
        self.remedy = ('İlgili profili kullanan diğer Manager / launcher görevini durdurun veya tamamlanmasını bekleyip yeniden deneyin.' if busy else
                       'Kendi Windows hesabınızla %LOCALAPPDATA%\\AWCenter erişimini, disk alanını ve güvenlik yazılımı politikasını kontrol edin; rapordaki sistem kodunu kullanın.')
        for label, value in (('WinError', getattr(system_error, 'winerror', None)),
                             ('errno', getattr(system_error, 'errno', None))):
            if type(value) is int and value > 0:
                message += f' {label}: {value}.'
        super().__init__(message)


def path_key(path: Path) -> str:
    require_unlinked(path)
    return 'path:' + os.path.normcase(str(Path(path).resolve()))


def path_claims(path: Path, *, write=False) -> dict[str, bool]:
    path = Path(path).absolute()
    claims = {path_key(parent): False for parent in path.parents}
    claims[path_key(path)] = write
    return claims


class _Lease:
    def __init__(self, path, write):
        require_unlinked(path)
        if path.exists():
            require_private(path)
        self.stream = path.open('a+b')
        self.write = write
        try:
            secure_path(path)
            try:
                self._lock(write)
            except OSError as error:
                # EACCES denotes contention only at the locking call, never
                # while opening storage. Windows access denial is not a lease.
                winerror = getattr(error, 'winerror', None)
                busy = (winerror == 33 or
                        (winerror is None and error.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}))
                raise ResourceLockError(busy=busy, system_error=error) from None
        except BaseException:
            self.stream.close()
            raise

    def _windows(self, *, lock, write=False):
        import ctypes
        from ctypes import wintypes
        import msvcrt
        class Overlapped(ctypes.Structure):
            _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                        ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        function = kernel.LockFileEx if lock else kernel.UnlockFileEx
        function.restype = wintypes.BOOL
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(self.stream.fileno()))
        overlap = Overlapped()
        args = (handle, 1 | (2 if write else 0), 0, 1, 0, ctypes.byref(overlap)) if lock else (
            handle, 0, 1, 0, ctypes.byref(overlap))
        if not function(*args):
            raise ctypes.WinError(ctypes.get_last_error())

    def _lock(self, write):
        if os.name == 'nt':
            self._windows(lock=True, write=write)
        else:
            import fcntl
            fcntl.flock(self.stream, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)

    def downgrade(self):
        if not self.write:
            return
        if os.name == 'nt':
            # LockFileEx permits a shared lock over our exclusive lock on the
            # same handle. The first unlock releases the exclusive lock only.
            self._windows(lock=True)
            self._windows(lock=False)
        else:
            self._lock(False)
        self.write = False

    def close(self):
        # Closing the handle releases even overlapping Windows locks on errors.
        self.stream.close()


@contextmanager
def resource_locks(home: Path, claims: dict[str, bool]):
    try:
        directory = private_directory(private_directory(Path(home)) / 'locks')
    except OSError as error:
        raise ResourceLockError(system_error=error) from None
    held = dict(_held.get() or {})
    acquired = []
    token = None
    try:
        for name, write in sorted(claims.items()):
            identity = (str(directory.resolve()), name)
            if identity in held:
                if write and not held[identity].write:
                    raise LauncherError('Çalışan kaynak üzerinde kurulum yapılamaz; önce ilgili profili durdurun.')
                continue
            filename = hashlib.sha256(name.encode('utf-8')).hexdigest() + '.lock'
            try:
                lease = _Lease(directory / filename, write)
            except OSError as error:
                raise ResourceLockError(system_error=error) from None
            held[identity] = lease
            acquired.append(lease)
        token = _held.set(held)
        yield
    finally:
        if token is not None:
            _held.reset(token)
        for lease in reversed(acquired):
            lease.close()


def downgrade_runtime_claims():
    for (_, name), lease in (_held.get() or {}).items():
        if name == 'runtime' or name.startswith('path:'):
            lease.downgrade()


@contextmanager
def lifecycle_locks(home, project, profile, *, write=False):
    claims = {**path_claims(project.root, write=write), 'runtime': write, 'profile:' + profile: True}
    with resource_locks(home, claims):
        yield


def windows_lifecycle(profile):
    """Keep direct launcher dev/prod commands inside the same GUI/CLI fence."""
    def decorate(function):
        @wraps(function)
        def run(project, *args, **kwargs):
            if os.name != 'nt':
                return function(project, *args, **kwargs)
            from .installation_profiles import installation_home
            with lifecycle_locks(installation_home(), project, profile,
                                 write=bool(kwargs.get('build_frontend'))):
                return function(project, *args, **kwargs)
        return run
    return decorate
