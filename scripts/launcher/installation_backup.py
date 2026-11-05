"""Manager-only verified SQLite/private-artifact snapshots before migration.

The caller owns exclusive installation lifecycle locks throughout. Django callbacks
must use the launcher's bounded, cancellable child runner. A failed or interrupted
migration never retries itself; only a fully applied plan may complete postchecks.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid

from .installation_permissions import require_private, require_unlinked, secure_path
from .installation_profiles import read_profile_environment
from .model import LauncherError
from .process import OperationCancelled


def _digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _sync_directory(path):
    # Windows uses write-through namespace publication, not POSIX directory fsync.
    if os.name == 'nt':
        raise LauncherError('POSIX directory synchronization is unavailable on Windows')
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _windows_publish(source, target, *, replace=False):
    """Use documented write-through file/directory moves; never silently degrade."""
    import ctypes
    from ctypes import wintypes
    native = ctypes.WinDLL('kernel32', use_last_error=True)
    native.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    native.MoveFileExW.restype = wintypes.BOOL
    flags = 0x8 | (0x1 if replace else 0)  # WRITE_THROUGH | REPLACE_EXISTING
    if not native.MoveFileExW(str(source), str(target), flags):
        raise LauncherError('Durable migration snapshot publication failed')


def _publish(source, target, *, replace=False):
    require_unlinked(source)
    require_unlinked(target)
    if not replace and target.exists():
        raise LauncherError('Migration snapshot destination already exists')
    if os.name == 'nt':
        _windows_publish(source, target, replace=replace)
        return
    os.replace(source, target)
    _sync_directory(target.parent)
    if source.parent != target.parent:
        _sync_directory(source.parent)


def _mkdir_private(path):
    temporary = path.parent / ('.pending-' + uuid.uuid4().hex)
    temporary.mkdir(mode=0o700)
    secure_path(temporary)
    if os.name != 'nt':
        _sync_directory(temporary)
    _publish(temporary, path)


def _flush_snapshot(directory, check):
    """Flush the complete tree before publishing the durable migration fence."""
    for current, _, files in os.walk(directory, topdown=False):
        check()
        for name in files:
            path = Path(current) / name
            require_private(path)
            with path.open('r+b') as stream:
                os.fsync(stream.fileno())
        if os.name != 'nt':
            _sync_directory(Path(current))
    if os.name == 'nt':
        # Microsoft documents WRITE_THROUGH MoveFileEx for directories and their
        # children. Stage and republish the complete tree before the start marker.
        staged = directory.parent / ('.publishing-' + uuid.uuid4().hex)
        _publish(directory, staged)
        _publish(staged, directory)
    else:
        _sync_directory(directory.parent)


def _write_json(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        secure_path(temporary)
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    _publish(temporary, path, replace=True)


def _read_receipt(path):
    require_private(path)
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('status') not in {'started', 'failed', 'verified', 'snapshot_started', 'snapshot_verified', 'snapshot_failed'}:
            raise ValueError
        return value
    except (ValueError, OSError, UnicodeError):
        raise LauncherError('Migration receipt verification failed') from None


def has_unresolved_migration(profile):
    """Read-only Manager routing check; never create or repair receipt storage."""
    if profile['name'] not in {'dev', 'prod'}:
        raise LauncherError('Unknown migration profile')
    backups = Path(profile['installation_home']) / 'backups' / profile['name']
    require_unlinked(backups)
    if not backups.exists():
        return False
    require_private(backups)
    for directory in backups.iterdir():
        require_private(directory)
        path = directory / 'receipt.json'
        if not path.exists():
            raise LauncherError('Incomplete migration snapshot requires operator inspection')
        if _read_receipt(path)['status'] in {'started', 'failed'}:
            return True
    return False


def _hash(path, check):
    require_unlinked(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise LauncherError('Backup input must be an unlinked regular file')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            check()
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise LauncherError('Backup input changed during verification')
    return digest.hexdigest()


def _media_inventory(root, check):
    require_unlinked(root)
    if not root.exists():
        return {}
    require_private(root)
    result = {}
    for directory, folders, files in os.walk(root, followlinks=False):
        check()
        for name in folders:
            folder = Path(directory) / name
            require_private(folder)
            result[folder.relative_to(root).as_posix() + '/'] = None
        for name in files:
            path = Path(directory) / name
            require_private(path)
            result[path.relative_to(root).as_posix()] = _hash(path, check)
    return result


def _copy_media(source, destination, inventory, check):
    _mkdir_private(destination)
    for relative, expected in inventory.items():
        check()
        target = destination / relative
        if expected is None:
            if not target.exists():
                _mkdir_private(target)
            require_private(target)
            continue
        missing = []
        parent = target.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for parent in reversed(missing):
            _mkdir_private(parent)
        temporary = target.parent / ('.artifact-' + uuid.uuid4().hex)
        with (source / relative).open('rb') as incoming, temporary.open('xb') as outgoing:
            secure_path(temporary)
            while True:
                check()
                block = incoming.read(1024 * 1024)
                if not block:
                    break
                outgoing.write(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        _publish(temporary, target)
        if _hash(target, check) != expected:
            raise LauncherError('Private artifact backup verification failed')


def _identity(database):
    require_unlinked(database)
    information = database.stat()
    return {'device': information.st_dev, 'inode': information.st_ino,
            'path_sha256': _digest_json(str(database.absolute()))}


def _source_hash(project, check):
    files = {}
    for path in sorted((project.root / 'backend').glob('**/migrations/*.py')):
        files[path.relative_to(project.root).as_posix()] = _hash(path, check)
    if not files:
        raise LauncherError('Migration sources could not be verified')
    return _digest_json(files)


def _reject_journals(database):
    for suffix in ('-wal', '-journal'):
        path = Path(str(database) + suffix)
        require_unlinked(path)
        if path.exists():
            raise LauncherError('SQLite must be quiescent before automatic migration')


def _verify_backup(directory, manifest, check):
    require_private(directory)
    database = directory / 'database.sqlite3'
    require_private(database)
    if _hash(database, check) != manifest['database_sha256']:
        raise LauncherError('Database backup hash verification failed')
    try:
        with contextlib.closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1)) as connection:
            connection.set_progress_handler(lambda: (check() or 0), 1000)
            if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise LauncherError('Database backup integrity verification failed')
    except sqlite3.Error:
        # sqlite converts exceptions in a progress handler into SQLITE_INTERRUPT.
        # Recheck the cooperative stop signal to preserve OperationCancelled.
        check()
        raise LauncherError('Database backup integrity verification failed') from None
    if _media_inventory(directory / 'private_media', check) != manifest['media']:
        raise LauncherError('Private artifact backup verification failed')


def run_backed_up_migrations(project, profile, inspect_backend, migrate, postcheck,
                             progress=None, *, cancelled=None, timeout=120, before_migrate=None):
    """Prepare a verified snapshot then invoke zero-argument migration callbacks.

    Returns a sanitized receipt dict, with ``backup_directory`` when applicable.
    ``inspect_backend`` returns installation_probe metadata; ``postcheck`` raises
    on a failed check. Optional ``before_migrate`` runs after snapshot verification,
    before the durable migration-start marker; its cancellation propagates intact. Callbacks must themselves enforce cancellation/time bounds.
    No rollback, fake migration, schema repair or secret persistence is performed.
    """
    deadline = time.monotonic() + timeout

    def check():
        if (cancelled and cancelled()) or time.monotonic() >= deadline:
            raise LauncherError('Migration preparation cancelled or timed out')

    def notify(message):
        check()
        if progress:
            progress(message)

    check()
    home = Path(profile['installation_home'])
    require_private(home)
    if profile['name'] not in {'dev', 'prod'}:
        raise LauncherError('Unknown migration profile')
    environment = read_profile_environment(profile)
    url = environment.get('DATABASE_URL', '')
    if not url.startswith('sqlite:///'):
        raise LauncherError('Automatic migration requires isolated SQLite storage')
    database = Path(url[len('sqlite:///'):])
    media = Path(environment['PRIVATE_MEDIA_ROOT'])
    if not database.is_absolute() or not media.is_absolute() or media == database or database.is_relative_to(media):
        raise LauncherError('Unsafe migration storage paths')
    require_unlinked(database)
    require_unlinked(media)
    backup_root = home / 'backups'
    environment_file = Path(profile['env_file'])
    if (media.is_relative_to(backup_root) or backup_root.is_relative_to(media)
            or database.is_relative_to(backup_root) or environment_file.is_relative_to(media)
            or database == environment_file or project.root.is_relative_to(media)):
        raise LauncherError('Migration storage overlaps a protected namespace')
    if Path(profile['source_root']).resolve() != project.root.resolve():
        raise LauncherError('Migration source identity mismatch')
    _reject_journals(database)
    state = inspect_backend()
    binding = {'profile_sha256': _digest_json(profile), 'environment_sha256': _hash(Path(profile['env_file']), check),
               'source_sha256': _source_hash(project, check)}
    backups = home / 'backups' / profile['name']
    for path in (home / 'backups', backups):
        require_unlinked(path)
        if not path.exists():
            _mkdir_private(path)
        require_private(path)
    # Incomplete receipts are a durable boundary, even after a process crash.
    for directory in sorted(backups.iterdir()):
        require_private(directory)
        receipt_path = directory / 'receipt.json'
        if not receipt_path.is_file():
            raise LauncherError('Incomplete migration snapshot requires operator inspection')
        previous = _read_receipt(receipt_path)
        if previous['status'] in {'verified', 'snapshot_started', 'snapshot_verified', 'snapshot_failed'}:
            continue
        if (state['schema'] != 'ready' or not state.get('auto_migrate_safe') or previous.get('binding') != binding
                or previous.get('database_identity') != _identity(database)
                or state.get('migration_plan', {}).get('required') != previous.get('plan', {}).get('required')
                or state.get('migration_plan', {}).get('source_sha256') != previous.get('plan', {}).get('source_sha256')):
            raise LauncherError('Incomplete migration requires operator inspection; automatic retry refused')
        if not previous.get('initialized'):
            manifest_path = directory / 'manifest.json'
            require_private(manifest_path)
            manifest = json.loads(manifest_path.read_text())
            if _digest_json(manifest) != previous.get('manifest_sha256'):
                raise LauncherError('Migration manifest verification failed')
            _verify_backup(directory, manifest, check)
        postcheck()
        previous['status'] = 'verified'
        _write_json(receipt_path, previous)
    if state['schema'] == 'ready':
        if not state.get('auto_migrate_safe'):
            raise LauncherError('Unknown or unsupported database schema; automatic migration refused')
        postcheck()
        return {'status': 'verified'}
    fresh = not database.exists() or database.stat().st_size == 0
    initializing = state['schema'] == 'missing' and fresh
    if not initializing and (state['schema'] != 'pending' or not state.get('auto_migrate_safe')):
        raise LauncherError('Unknown or unsupported database schema; automatic migration refused')
    if initializing and not database.exists():
        database.touch(mode=0o600)
        secure_path(database)
    require_private(database)
    notify('Boş veritabanı hazırlanıyor' if initializing else 'Veritabanı ve özel dosya yedeği doğrulanıyor')
    directory = backups / uuid.uuid4().hex
    _mkdir_private(directory)
    receipt_path = directory / 'receipt.json'
    receipt = {'status': 'snapshot_started', 'binding': binding, 'database_identity': _identity(database),
               'plan': state['migration_plan'], 'backup_directory': str(directory), 'initialized': initializing}
    _write_json(receipt_path, receipt)
    confirmation_pending = False
    try:
        if initializing:
            receipt['status'] = 'snapshot_verified'
            _write_json(receipt_path, receipt)
            confirmation_pending = True
            if before_migrate:
                before_migrate()
            confirmation_pending = False
            check()
            if (binding['environment_sha256'] != _hash(Path(profile['env_file']), check)
                    or binding['source_sha256'] != _source_hash(project, check)
                    or _identity(database) != receipt['database_identity']
                    or database.stat().st_size != 0
                    or inspect_backend().get('migration_plan') != state.get('migration_plan')):
                raise LauncherError('Initialization inputs changed during confirmation')
            _flush_snapshot(directory, check)
            receipt['status'] = 'started'
            _write_json(receipt_path, receipt)
            migrate()
            check()
            result = inspect_backend()
            if (result['schema'] != 'ready' or not result.get('auto_migrate_safe')
                    or _identity(database) != receipt['database_identity']):
                raise LauncherError('Database initialization verification failed')
            postcheck()
            receipt['status'] = 'verified'
            _write_json(receipt_path, receipt)
            return receipt
        with contextlib.closing(sqlite3.connect(database, timeout=0.1)) as guard:
            # A reserved write lock detects other writers and prevents writes until
            # DB and media snapshots and their source hashes have been verified.
            guard.execute('BEGIN IMMEDIATE')
            original_hash = _hash(database, check)
            inventory = _media_inventory(media, check)
            target = directory / '.database.pending'
            target.touch(mode=0o600)
            secure_path(target)
            with contextlib.closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1)) as source:
                with contextlib.closing(sqlite3.connect(target)) as destination:
                    source.backup(destination, pages=128, progress=lambda *_: check(), sleep=0.01)
            with target.open('r+b') as stream:
                os.fsync(stream.fileno())
            _publish(target, directory / 'database.sqlite3')
            target = directory / 'database.sqlite3'
            _copy_media(media, directory / 'private_media', inventory, check)
            manifest = {'binding': binding, 'database_identity': receipt['database_identity'],
                        'plan': receipt['plan'], 'database_sha256': _hash(target, check), 'media': inventory}
            _verify_backup(directory, manifest, check)
            if (inventory != _media_inventory(media, check) or original_hash != _hash(database, check)
                    or _identity(database) != receipt['database_identity']):
                raise LauncherError('Source data changed during migration snapshot')
            if binding != {'profile_sha256': _digest_json(profile), 'environment_sha256': _hash(Path(profile['env_file']), check), 'source_sha256': _source_hash(project, check)}:
                raise LauncherError('Migration inputs changed during snapshot')
            _write_json(directory / 'manifest.json', manifest)
            receipt['manifest_sha256'] = _digest_json(manifest)
            receipt['status'] = 'snapshot_verified'
            _write_json(receipt_path, receipt)
            confirmation_pending = True
            if before_migrate:
                before_migrate()
            confirmation_pending = False
            check()
            # Confirmation may wait for an operator. Revalidate mutable inputs
            # while the SQLite reservation still excludes concurrent writers.
            if (inventory != _media_inventory(media, check) or original_hash != _hash(database, check)
                    or _identity(database) != receipt['database_identity']
                    or binding['environment_sha256'] != _hash(Path(profile['env_file']), check)
                    or binding['source_sha256'] != _source_hash(project, check)
                    or inspect_backend().get('migration_plan') != state.get('migration_plan')):
                raise LauncherError('Migration inputs changed during confirmation')
            _verify_backup(directory, manifest, check)
            _flush_snapshot(directory, check)
            receipt['status'] = 'started'
            _write_json(receipt_path, receipt)
            guard.rollback()
        notify('Yedek doğrulandı; veritabanı güncelleniyor')
        migrate()
        check()
        result = inspect_backend()
        if (result['schema'] != 'ready' or not result.get('auto_migrate_safe')
                or _identity(database) != receipt['database_identity']):
            raise LauncherError('Migration result verification failed')
        postcheck()
        receipt['status'] = 'verified'
        _write_json(receipt_path, receipt)
        return receipt
    except BaseException as error:
        if confirmation_pending:
            raise
        receipt['status'] = 'failed' if receipt['status'] == 'started' else 'snapshot_failed'
        _write_json(receipt_path, receipt)
        if isinstance(error, (KeyboardInterrupt, SystemExit, OperationCancelled)):
            raise
        raise LauncherError('Migration stopped; snapshot retained for operator inspection') from None
