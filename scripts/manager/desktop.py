"""Windowless Windows Manager activation and current-user desktop integration."""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Literal
from uuid import UUID

Action = Literal['open', 'settings']
_POINTER = ctypes.c_void_p
_TEXT = ctypes.c_wchar_p


def _instance_name() -> str:
    # TokenUser begins with a SID pointer. Read the token locally, including
    # on disconnected domain machines. Local\ selects the Windows session.
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    info = advapi.GetTokenInformation
    info.argtypes = [_POINTER, ctypes.c_int, _POINTER, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    size = wintypes.DWORD()
    token = _POINTER(-4)  # GetCurrentProcessToken() pseudo-handle.
    info(token, 1, None, 0, ctypes.byref(size))
    if not size.value:
        raise ctypes.WinError(ctypes.get_last_error())
    data = ctypes.create_string_buffer(size.value)
    if not info(token, 1, data, len(data), ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    sid = ctypes.cast(data, ctypes.POINTER(_POINTER))[0]
    advapi.GetLengthSid.argtypes = [_POINTER]
    sid_bytes = ctypes.string_at(sid, advapi.GetLengthSid(sid))
    return 'Local\\AWCenterManager.' + hashlib.sha256(sid_bytes).hexdigest()


def _kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateEventW.argtypes = [_POINTER, wintypes.BOOL, wintypes.BOOL, _TEXT]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.CreateMutexW.argtypes = [_POINTER, wintypes.BOOL, _TEXT]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.ResetEvent.argtypes = kernel.SetEvent.argtypes = [wintypes.HANDLE]
    kernel.WaitForMultipleObjects.argtypes = [
        wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD]
    kernel.WaitForMultipleObjects.restype = wintypes.DWORD
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel


_OBJECT = 0
_ABANDONED = 128
_TIMEOUT = 258


def _check(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


class Instance:
    def __init__(self, kernel=None):
        self._kernel = kernel
        self._events: dict[Action, int] = {}
        self._ack: dict[Action, int] = {}
        self._mutex = None
        self._owns_mutex = False

    def _connect(self, name):
        self._mutex = _check(self._kernel.CreateMutexW(None, False, name + '.owner'))
        for action in ('settings', 'open'):
            self._events[action] = _check(self._kernel.CreateEventW(None, False, False, f'{name}.{action}'))
            self._ack[action] = _check(self._kernel.CreateEventW(None, True, False, f'{name}.{action}.ack'))

    def _acquire_or_signal(self, action):
        result = self._kernel.WaitForSingleObject(self._mutex, 0)
        if result in {_OBJECT, _ABANDONED}:
            self._owns_mutex = True
            return True
        if result != _TIMEOUT:
            raise ctypes.WinError(ctypes.get_last_error())

        _check(self._kernel.ResetEvent(self._ack[action]))
        _check(self._kernel.SetEvent(self._events[action]))
        # Only the new, windowless process waits. Normally the Tk poll confirms
        # within 100 ms. If the UI exited first, this thread acquires its mutex.
        handles = (wintypes.HANDLE * 2)(self._ack[action], self._mutex)
        result = self._kernel.WaitForMultipleObjects(2, handles, False, 30_000)
        if result in {_OBJECT, _TIMEOUT}:
            # A busy owner's pending request remains signaled after the timeout.
            return False
        if result not in {_OBJECT + 1, _ABANDONED + 1}:
            raise ctypes.WinError(ctypes.get_last_error())
        self._owns_mutex = True
        self._consume(action)
        return True

    def _consume(self, action):
        result = self._kernel.WaitForSingleObject(self._events[action], 0)
        if result == _TIMEOUT:
            return False
        if result != _OBJECT:
            raise ctypes.WinError(ctypes.get_last_error())
        _check(self._kernel.SetEvent(self._ack[action]))
        return True

    def poll(self) -> Action | None:
        """Consume at most one pending activation without blocking the UI."""
        return next((action for action in self._events if self._consume(action)), None)

    def close(self):
        """Release the ownership mutex on the acquiring thread after UI shutdown."""
        for handles in (self._events, self._ack):
            for handle in handles.values():
                self._kernel.CloseHandle(handle)
            handles.clear()
        if self._mutex:
            if self._owns_mutex:
                self._kernel.ReleaseMutex(self._mutex)
            self._kernel.CloseHandle(self._mutex)
            self._mutex = None


def acquire_instance(settings: bool = False) -> Instance | None:
    """Signal a running Manager, or acquire ownership if it finished closing.

    A Windows IPC error raises OSError so startup can fail visibly and safely.
    On other platforms the returned owner has no activation events.
    """
    if sys.platform != 'win32':
        return Instance()
    owner = Instance(_kernel())
    with ExitStack() as cleanup:
        cleanup.callback(owner.close)
        owner._connect(_instance_name())
        if not owner._acquire_or_signal('settings' if settings else 'open'):
            return None
        cleanup.pop_all()
        return owner


def _shortcut_target() -> tuple[Path, str, Path]:
    executable = Path(sys.executable).absolute()
    if getattr(sys, 'frozen', False):
        return executable, '', executable.parent
    script = Path(__file__).resolve().parents[2] / 'AWCenterManager.pyw'
    if not script.is_file():
        raise FileNotFoundError(script)
    return executable.with_name('pythonw.exe'), subprocess.list2cmdline([str(script)]), script.parent


def _desktop_directory() -> Path:
    # FOLDERID_Desktop respects OneDrive and redirected user desktops.
    folder = UUID('b4bfcc3a-db2c-424c-b029-7fe99a87c641').bytes_le
    result = _TEXT()
    try:
        ctypes.oledll.shell32.SHGetKnownFolderPath(folder, 0, None, ctypes.byref(result))
        return Path(result.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(result)


def _method(index, name, *argtypes):
    """Bind an HRESULT-returning Shell COM method by its SDK vtable slot."""
    return ctypes.WINFUNCTYPE(ctypes.HRESULT, *argtypes)(index, name)


@contextmanager
def _shell_link():
    ole = ctypes.oledll.ole32
    link = _POINTER()
    persist = _POINTER()
    shell_class = UUID('00021401-0000-0000-c000-000000000046').bytes_le
    shell_interface = UUID('000214f9-0000-0000-c000-000000000046').bytes_le
    persist_interface = UUID('0000010b-0000-0000-c000-000000000046').bytes_le
    ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
    with ExitStack() as cleanup:
        cleanup.callback(ctypes.windll.ole32.CoUninitialize)
        release = ctypes.WINFUNCTYPE(wintypes.ULONG)(2, 'Release')
        ole.CoCreateInstance(shell_class, None, 1, shell_interface, ctypes.byref(link))
        cleanup.callback(release, link)
        _method(0, 'QueryInterface', _POINTER, _POINTER)(link, persist_interface, ctypes.byref(persist))
        cleanup.callback(release, persist)
        yield link, persist


def _matches_shortcut(path: Path, target: Path, arguments: str) -> bool:
    attributes = path.lstat()
    if (not stat.S_ISREG(attributes.st_mode)
            or getattr(attributes, 'st_reparse_tag', 0) & 0x20000000):  # name-surrogate reparse tag
        return False
    with _shell_link() as (link, persist):
        _method(5, 'Load', _TEXT, wintypes.DWORD)(persist, str(path), 0)
        saved_path = ctypes.create_unicode_buffer(32768)
        saved_args = ctypes.create_unicode_buffer(32768)
        _method(3, 'GetPath', _TEXT, ctypes.c_int, _POINTER, wintypes.DWORD)(
            link, saved_path, len(saved_path), None, 0)
        _method(10, 'GetArguments', _TEXT, ctypes.c_int)(link, saved_args, len(saved_args))
        return Path(saved_path.value) == target and saved_args.value == arguments


def _save_shortcut(path: Path, target: Path, arguments: str, directory: Path):
    with _shell_link() as (link, persist):
        _method(20, 'SetPath', _TEXT)(link, str(target))
        _method(11, 'SetArguments', _TEXT)(link, arguments)
        _method(9, 'SetWorkingDirectory', _TEXT)(link, str(directory))
        _method(6, 'Save', _TEXT, wintypes.BOOL)(persist, str(path), True)


def create_desktop_shortcut() -> bool:
    """Ensure AW Center.lnk launches this installation. Preserve conflicting files."""
    if sys.platform != 'win32':
        return False
    from _ctypes import COMError
    try:
        target, arguments, directory = _shortcut_target()
        if not target.is_file():
            return False
        destination = _desktop_directory() / 'AW Center.lnk'
        if os.path.lexists(destination):
            return _matches_shortcut(destination, target, arguments)
        # Keep relative shell-link metadata anchored to the final directory.
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.lnk', delete=False) as staging:
            temporary = Path(staging.name)
        try:
            _save_shortcut(temporary, target, arguments, directory)
            # On Windows rename fails if another launcher already published.
            try:
                temporary.rename(destination)
            except FileExistsError:
                return _matches_shortcut(destination, target, arguments)
        finally:
            temporary.unlink(missing_ok=True)
        return True
    except (OSError, COMError):
        return False
