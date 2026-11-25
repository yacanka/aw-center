"""Keep a validated read-only source available while replacing network snapshots."""

from contextlib import suppress
import ctypes
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from stat import FILE_ATTRIBUTE_REPARSE_POINT, S_ISREG
from tempfile import NamedTemporaryFile
from threading import Event, RLock


class SourceError(ValueError):
    """A short error suitable for the viewer's file picker or refresh banner."""


def is_network_path(path):
    if str(path).startswith('\\\\'):
        return True
    # A mapped drive letter can point at an SMB share too.
    return os.name == 'nt' and ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4


def _check_local_path(path):
    if os.name == 'nt':
        # A junction under a local drive may redirect live SQLite reads to a network host.
        for component in (*reversed(path.parents), path):
            if component.lstat().st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                raise SourceError('Bağlantı veya junction içermeyen gerçek dosya yolunu girin.')
    if not S_ISREG(path.stat().st_mode):
        raise SourceError('Seçilen yol normal bir dosya olmalı.')


def _backup_version(path):
    info = path.stat()
    if not S_ISREG(info.st_mode):
        raise SourceError('Seçilen yol normal bir dosya olmalı.')
    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise SourceError('Ağda tamamlanmış, bağımsız bir SQLite yedeği seçin.')
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _copy_backup(source, directory, check_open):
    version = _backup_version(source)
    with NamedTemporaryFile(dir=directory, suffix='.db', delete=False) as output:
        destination = Path(output.name)
    try:
        with source.open('rb') as src, destination.open('wb') as dst:
            while chunk := src.read(1024 * 1024):
                check_open()
                dst.write(chunk)
        if _backup_version(source) != version or destination.stat().st_size != version[2]:
            raise SourceError('Kopyalama sırasında yedek değişti. Yeniden deneyin.')
        with destination.open('rb') as copied:
            if copied.read(16) != b'SQLite format 3\x00':
                raise SourceError('Seçilen dosya bir SQLite yedeği değil.')
        return destination
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


class DatabaseSource:
    def __init__(self, directory, reader_factory, network_path=is_network_path):
        self.directory = directory
        self.reader_factory = reader_factory
        self.network_path = network_path
        self._writer = RLock()
        self._state = RLock()
        self._stopping = Event()
        self.path = None
        self._snapshot = None
        self._reader = None
        self._status = {}

    def _check_open(self):
        if self._stopping.is_set():
            raise SourceError('Görüntüleyici kapanıyor.')

    def select(self, path):
        with self._writer:
            self._check_open()
            candidate = None
            try:
                network = self.network_path(path)
                if network:
                    candidate = _copy_backup(path, self.directory, self._check_open)
                    reader = self.reader_factory(candidate, immutable=True)
                else:
                    _check_local_path(path)
                    reader = self.reader_factory(path)
                projects = reader.projects()
                self._check_open()
            except (OSError, sqlite3.Error, ValueError) as exc:
                if candidate:
                    candidate.unlink(missing_ok=True)
                message = _source_message(exc)
                with self._state:
                    self._status['warning'] = message
                raise SourceError(message) from exc

            # Reads hold this lock until SQLite closes. The slower copy/validation above
            # leaves a previous good snapshot available throughout network outages.
            with self._state:
                previous = self._snapshot
                self._snapshot, self._reader, self.path = candidate, reader, path
                self._status = {
                    'source_kind': 'backup' if network else 'local',
                    'projects': projects,
                    'read_at': datetime.now(timezone.utc).isoformat(),
                    'warning': '',
                }
            if previous:
                with suppress(OSError):
                    previous.unlink(missing_ok=True)
            return self.status()

    def refresh(self):
        with self._writer:
            self._check_open()
            if self.path is None:
                raise SourceError('Önce bir veritabanı seçin.')
            return self.select(self.path)

    def status(self):
        with self._state:
            return self._status.copy()

    def read(self, kind, slug):
        with self._state:
            self._check_open()
            if self._reader is None or kind not in ('dashboard', 'documents'):
                raise LookupError
            return getattr(self._reader, kind)(slug)

    def request_stop(self):
        self._stopping.set()

    def close(self):
        self.request_stop()
        with self._writer, self._state:
            self._reader = None
            if self._snapshot:
                self._snapshot.unlink(missing_ok=True)
                self._snapshot = None


def _source_message(exc):
    if isinstance(exc, SourceError):
        return str(exc)
    if isinstance(exc, PermissionError):
        return 'Dosyayı okumak için Windows erişim izni gerekiyor.'
    if isinstance(exc, FileNotFoundError):
        return 'Veritabanı bulunamadı.'
    return 'Veritabanı okunamadı. Dosyanın erişilebilir, tamamlanmış ve AW Center ile uyumlu olduğunu kontrol edin.'
