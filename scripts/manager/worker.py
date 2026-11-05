"""Gated private IPC for one desktop worker, with no Tk or task-global state."""
from __future__ import annotations

import argparse
import io
import json
import os
import queue
import sys
import threading
import uuid

from scripts.launcher.model import LauncherError
from scripts.launcher.process import OperationCancelled
# Kept as module exports for existing headless callers of the worker.
from .operations import arguments, execute, _failure_reason

MAX_MESSAGE = 64 * 1024


class _Discard(io.TextIOBase):
    def write(self, value):
        return len(value)
    def flush(self):
        pass


def main(argv=None):
    _restore_private_streams()
    # Source/python.exe runs can use a Windows ANSI code page for pipes, while
    # the owner decodes the protocol as UTF-8. Never use the host text encoding.
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    parser = argparse.ArgumentParser()
    parser.add_argument('--manager-gate', action='store_true')
    args = parser.parse_args(argv)
    if not args.manager_gate or os.read(sys.stdin.fileno(), 3) != b'go\n':
        return 2
    channel = sys.stdout
    sys.stdout = sys.stderr = _Discard()
    lock = threading.Lock()
    def emit(event):
        encoded = json.dumps(event, ensure_ascii=False)
        if len(encoded.encode('utf-8')) > MAX_MESSAGE:
            raise LauncherError('Yönetim raporu boyut sınırını aştı.')
        with lock:
            channel.write(encoded + '\n')
            channel.flush()
    if os.name == 'nt' and getattr(sys, 'frozen', False):
        # PyInstaller's Tcl/Python DLL search must not affect Node/LibreOffice.
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    stop, inbox = threading.Event(), queue.Queue(maxsize=1)
    awaiting = {'kind': None, 'id': None}
    pending = bytearray()
    def read_line():
        # A daemon must never block holding stdin's BufferedReader lock during
        # interpreter shutdown. Keep only our own bounded buffer around os.read.
        while b'\n' not in pending:
            chunk = os.read(sys.stdin.fileno(), 4096)
            if not chunk or len(pending) + len(chunk) > MAX_MESSAGE:
                raise ValueError('Invalid desktop request')
            pending.extend(chunk)
        boundary = pending.index(b'\n') + 1
        line = bytes(pending[:boundary])
        del pending[:boundary]
        return json.loads(line)
    try:
        request = read_line()
    except Exception:
        return 2
    def controls():
        try:
            while True:
                value = read_line()
                if value.get('type') == 'cancel':
                    stop.set()
                elif (value.get('type') == awaiting['kind'] and
                      (awaiting['kind'] == 'admin' or value.get('request_id') == awaiting['id'])):
                    try:
                        inbox.put_nowait(value.get('value'))
                    except queue.Full:
                        pass  # A duplicate reply cannot cancel another prompt.
        except Exception:
            stop.set()  # Loss of the owning GUI never leaves a running server.
    threading.Thread(target=controls, daemon=True).start()
    def input_provider(kind):
        request_id = uuid.uuid4().hex
        awaiting.update(kind=kind, id=request_id)
        emit({'type': 'input', 'kind': kind, 'request_id': request_id})
        while True:
            if stop.is_set():
                raise OperationCancelled()
            try:
                result = inbox.get(timeout=0.2)
                awaiting.update(kind=None, id=None)
                if result is None or (kind == 'migration' and result is not True):
                    raise OperationCancelled()
                return result
            except queue.Empty:
                continue
    execute(request, emit, lambda: input_provider('admin'), stop,
            migration_provider=lambda: input_provider('migration'))
    return 0


def _restore_private_streams():
    """PyInstaller windowed Python has no streams, even with inherited pipes.

    Duplicate only the parent's explicit stdin/stdout pipe handles; never attach
    a console, create a network listener, or fall back to a public temp file.
    """
    if os.name != 'nt' or (sys.stdin is not None and sys.stdout is not None):
        return
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                     ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.DuplicateHandle.restype = wintypes.BOOL
    owner = kernel.GetCurrentProcess()
    for name, number, reading in (('stdin', -10, True), ('stdout', -11, False)):
        if getattr(sys, name) is not None:
            continue
        handle = kernel.GetStdHandle(number & 0xffffffff)
        duplicate = wintypes.HANDLE()
        if not kernel.DuplicateHandle(owner, handle, owner, ctypes.byref(duplicate), 0, False, 2):
            raise OSError('Private desktop pipe unavailable')
        flags = os.O_BINARY | (os.O_RDONLY if reading else os.O_WRONLY)
        descriptor = msvcrt.open_osfhandle(duplicate.value, flags)
        stream = os.fdopen(descriptor, 'rb' if reading else 'wb', buffering=0)
        setattr(sys, name, io.TextIOWrapper(stream, encoding='utf-8', line_buffering=not reading))


if __name__ == '__main__':
    raise SystemExit(main())
