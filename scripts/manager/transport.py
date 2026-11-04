"""Private stdio transport; the GUI owns the worker's entire process tree."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time

from scripts.launcher.process import terminate
from .paths import worker_directory

MAX_MESSAGE = 64 * 1024
MAX_OUTBOUND = 8
IO_POLL_INTERVAL = 0.05
CANCEL_DELIVERY_TIMEOUT = 1.0
EVENT_TYPES = {'phase', 'status', 'checks', 'ready', 'error', 'input', 'done', 'profile', 'health'}


def _encode(value):
    encoded = (json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8')
    if len(encoded) > MAX_MESSAGE:
        raise ValueError('Desktop message exceeds limit')
    return encoded


def _write_all(stream, encoded):
    # Unbuffered pipes can accept fewer bytes than requested, including on Windows.
    remaining = memoryview(encoded)
    while remaining:
        written = stream.write(remaining)
        if written is None or written <= 0:
            raise BrokenPipeError('Desktop worker input is unavailable')
        remaining = remaining[written:]


def _failure_event(stage, error, child):
    """Expose fixed recovery text and numeric OS status, never exception data."""
    failures = {
        'request': ('worker_request_invalid', 'İşlem isteği hazırlanamadı.', 'Form alanlarını kontrol edip yeniden deneyin.'),
        'start': ('worker_start_failed', 'Yardımcı süreç başlatılamadı.', 'ZIP paketinin tamamını yerel bir klasöre çıkarın; uygulama çalıştırma izinlerini ve güvenlik yazılımının engelleme kayıtlarını kontrol edin.'),
        'containment': ('worker_containment_failed', 'Yardımcı süreç güvenli biçimde izole edilemedi.', 'Windows süreç kısıtlarını ve kurumun uygulama çalıştırma politikasını kontrol edin. Güvenli izolasyon kurulmadan işlem başlatılmaz.'),
        'channel': ('worker_channel_failed', 'Yardımcı süreçle iletişim kurulamadı veya kesildi.', 'Manager paketini güncelleyin. Aynı hata diğer işlemlerde de oluyorsa hata kodunu ve sayısal sistem kodunu bildirin.'),
        'protocol': ('worker_protocol_invalid', 'Yardımcı sürecin yanıtı okunamadı.', 'Manager paketini güncelleyin; EXE ve _internal dizini aynı pakete ait olmalı.'),
        'exit': ('worker_exited', 'Yardımcı süreç sonuç bildirmeden kapandı.', 'Paket bileşenlerini ve güvenlik yazılımının engelleme kayıtlarını kontrol edin; süreç çıkış kodunu bildirin.'),
    }
    code, message, remedy = failures[stage]
    if stage == 'start' and isinstance(error, PermissionError):
        code, message = 'worker_start_denied', 'Windows veya işletim sistemi yardımcı sürecin başlatılmasına izin vermedi.'
    system_code = getattr(error, 'winerror', None)
    if type(system_code) is not int:
        system_code = getattr(error, 'errno', None)
    if type(system_code) is int:
        message += f' Sistem hata kodu: {system_code}.'
    exit_code = getattr(child, 'returncode', None)
    if type(exit_code) is int:
        message += f' Süreç çıkış kodu: {exit_code}.'
    return {'type': 'error', 'code': code, 'message': message, 'remedy': remedy}


class WorkerSession:
    """One contained worker. GUI callbacks only enqueue controls or set Stop.

    ``run`` belongs on the controller's background thread. ``send`` raises a
    payload-free RuntimeError when its bounded queue is full or already closed;
    the desktop must report that failure instead of silently losing user input.
    """

    def __init__(self, emit):
        self.emit = emit
        self.child = None
        self._outbound = queue.Queue(maxsize=MAX_OUTBOUND)
        self._cancel = threading.Event()
        self._closed = threading.Event()
        self._writer_failed = threading.Event()
        self._cancel_sent = threading.Event()

    @property
    def running(self):
        return self.child is not None and self.child.poll() is None

    def send(self, value):
        encoded = _encode(value)
        if self._closed.is_set():
            raise RuntimeError('Desktop worker input is closed')
        if isinstance(value, dict) and value.get('type') == 'cancel':
            self.stop()
            return
        try:
            self._outbound.put_nowait(encoded)
        except queue.Full:
            raise RuntimeError('Desktop message queue is full') from None

    def stop(self):
        # Cancellation cannot wait behind a credential prompt or a full pipe.
        # This also survives Stop arriving before Popen returns.
        self._cancel.set()

    def _write_messages(self, child, request):
        try:
            _write_all(child.stdin, b'go\n')
            _write_all(child.stdin, request)
            while not self._closed.is_set():
                if self._cancel.is_set():
                    _write_all(child.stdin, b'{"type": "cancel"}\n')
                    self._cancel_sent.set()
                    return
                try:
                    encoded = self._outbound.get(timeout=IO_POLL_INTERVAL)
                except queue.Empty:
                    continue
                if not self._cancel.is_set() and not self._closed.is_set():
                    _write_all(child.stdin, encoded)
        except Exception:
            self._writer_failed.set()

    def _read_lines(self, child, lines):
        try:
            while not self._closed.is_set():
                line = child.stdout.readline(MAX_MESSAGE + 1)
                if not self._queue_line(lines, line) or not line:
                    return
        except Exception:
            self._queue_line(lines, None)

    def _queue_line(self, lines, line):
        while not self._closed.is_set():
            try:
                lines.put(line, timeout=IO_POLL_INTERVAL)
                return True
            except queue.Full:
                continue
        return False

    def run(self, request):
        done = False
        child = None
        threads = []
        stage = 'request'
        try:
            encoded = _encode(request)
            frozen = getattr(sys, 'frozen', False)
            command = ([sys.executable, '--manager-worker'] if frozen else
                       [sys.executable, '-m', 'scripts.manager.worker'])
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
            # Raw pipes do not hold BufferedWriter locks while an OS write stalls;
            # closing them during cleanup cannot wait for the writer's Python lock.
            stage = 'start'
            child = subprocess.Popen([*command, '--manager-gate'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                                     cwd=worker_directory(),
                                     **options)
            stage = 'containment'
            if os.name == 'nt':
                from scripts.launcher.windows_job import WindowsJob
                child._launcher_job = WindowsJob(child._handle)
            else:
                child._launcher_group = child.pid
            # Containment and ownership exist before the writer opens the gate.
            self.child = child
            stage = 'channel'
            lines = queue.Queue(maxsize=16)
            threads = [
                threading.Thread(target=self._write_messages, args=(child, encoded),
                                 name='awcenter-manager-writer', daemon=True),
                threading.Thread(target=self._read_lines, args=(child, lines),
                                 name='awcenter-manager-reader', daemon=True),
            ]
            for thread in threads:
                thread.start()
            cancel_deadline = None
            while True:
                stage = 'channel'
                if self._cancel.is_set() and not self._cancel_sent.is_set():
                    if cancel_deadline is None:
                        cancel_deadline = time.monotonic() + CANCEL_DELIVERY_TIMEOUT
                    if time.monotonic() >= cancel_deadline:
                        raise TimeoutError('Desktop worker did not accept cancellation')
                try:
                    line = lines.get(timeout=IO_POLL_INTERVAL)
                except queue.Empty:
                    if self._writer_failed.is_set():
                        raise BrokenPipeError('Desktop worker input is unavailable')
                    continue
                if line is None:
                    raise ValueError('Desktop worker output is unavailable')
                if not line:
                    break
                stage = 'protocol'
                if len(line) > MAX_MESSAGE:
                    raise ValueError('Desktop event exceeds limit')
                event = json.loads(line)
                if not isinstance(event, dict) or event.get('type') not in EVENT_TYPES:
                    raise ValueError('Invalid desktop event')
                if done:
                    raise ValueError('Unexpected event after task completion')
                done = event['type'] == 'done'
                self.emit(event)
            stage = 'exit'
            child.wait(timeout=10)
            if not done:
                raise ValueError('Worker exited without a result')
        except Exception as error:
            if not done:
                self.emit(_failure_event(stage, error, child))
                self.emit({'type': 'done', 'ok': False})
        finally:
            self._closed.set()
            try:
                if child is not None:
                    try:
                        terminate([child])
                    finally:
                        for stream in (child.stdin, child.stdout):
                            if stream is not None:
                                try:
                                    stream.close()
                                except (OSError, ValueError):
                                    pass
            finally:
                # A faulty OS write must never pin the owner thread or shutdown.
                for thread in threads:
                    if thread.ident is not None:
                        thread.join(timeout=0.2)
                self.child = None
                while True:
                    try:
                        self._outbound.get_nowait()
                    except queue.Empty:
                        break
