"""Sanitized backend inspection in the installed project interpreter.

Run ``python -m scripts.launcher.installation_probe inspect`` from the source root.
Inspection never opens Django's writable database connection or cache backend.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys

from .installation_permissions import require_unlinked
from .model import LauncherError


def inspect_sqlite(database: Path, required_migrations: set[tuple[str, str]], *, user_table='auth_user') -> dict:
    """Read an immutable SQLite snapshot, refusing active WAL rather than mutating it."""
    result = {'schema': 'missing', 'admin_exists': None, 'diagnostics': []}
    require_unlinked(database)
    if not database.is_file():
        return result
    # Immutable mode cannot see WAL changes. Do not pretend an old snapshot is ready.
    if Path(str(database) + '-wal').exists():
        result['schema'] = 'error'
        result['diagnostics'].append({'name': 'database', 'status': 'error', 'detail': 'Active SQLite WAL requires a quiescent inspection.'})
        return result
    try:
        with contextlib.closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as connection:
            connection.execute('PRAGMA query_only=ON')
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'django_migrations' not in tables:
                return result
            applied = set(connection.execute('SELECT app, name FROM django_migrations'))
            result['schema'] = 'ready' if required_migrations <= applied else 'pending'
            if user_table in tables:
                # The identifier comes from Django model metadata, never from operator input.
                quoted_table = '"' + user_table.replace('"', '""') + '"'
                result['admin_exists'] = connection.execute(f'SELECT 1 FROM {quoted_table} WHERE is_superuser = 1 AND is_active = 1 LIMIT 1').fetchone() is not None
    except (sqlite3.Error, OSError):
        result['schema'] = 'error'
        result['diagnostics'].append({'name': 'database', 'status': 'error', 'detail': 'Database inspection failed; details withheld.'})
    return result


def inspect_backend() -> dict:
    """Load Django metadata and inspect state without migration or external calls."""
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db.migrations.loader import MigrationLoader

    database = settings.DATABASES['default']
    if database['ENGINE'] != 'django.db.backends.sqlite3':
        return {'schema': 'error', 'admin_exists': None, 'diagnostics': [{'name': 'database', 'status': 'error', 'detail': 'Installation profiles require isolated SQLite storage.'}]}
    loader = MigrationLoader(None, ignore_no_migrations=True)
    required = set(loader.disk_migrations)
    result = inspect_sqlite(Path(database['NAME']), required, user_table=get_user_model()._meta.db_table)
    for name, enabled in (
        ('JIRA', settings.JIRA_ENABLED), ('DOORS', settings.DOORS_ENABLED),
        ('Teamcenter', settings.TEAMCENTER_ENABLED), ('DocProof', settings.DOCPROOF_ENABLED),
        ('Numarator', settings.NUMARATOR_ENABLED),
    ):
        result['diagnostics'].append({'name': name, 'status': 'configured' if enabled else 'missing', 'detail': 'Enabled; connectivity requires a separate operator check.' if enabled else 'Disabled until operator configuration is supplied.'})
    result['diagnostics'].append({'name': 'mail', 'status': 'configured' if settings.AWCENTER_MAIL_TRANSPORT == 'django' else 'missing', 'detail': 'Mail transport configuration inspected; no message sent.'})
    return result


def provision_admin_json(stream) -> dict:
    """Consume a bounded private stdin message; return only a declared status.

    This transport never places credentials in argv, environment, output or a
    temporary file. Validation details are deliberately withheld from the IPC.
    """
    try:
        payload = stream.read(16 * 1024 + 1)
        if len(payload) > 16 * 1024:
            raise ValueError
        content = json.loads(payload)
        if (not isinstance(content, dict) or set(content) != {'username', 'password'}
                or any(not isinstance(value, str) or not value for value in content.values())
                or len(content['username']) > 150 or len(content['password']) > 4096):
            raise ValueError
        from users.initial_admin import create_initial_admin
        created = create_initial_admin(content['username'], content['password'])
        return {'status': 'created' if created else 'exists'}
    except Exception:
        return {'status': 'error', 'code': 'invalid_admin_input'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Inspect installation backend without changing state.')
    parser.add_argument('operation', choices=['inspect', 'initial-admin', 'initial-admin-json'])
    arguments = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'awcenter.settings')
    sys.dont_write_bytecode = True
    if arguments.operation == 'initial-admin-json':
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                import django
                django.setup()
                result = provision_admin_json(sys.stdin)
        except Exception:
            result = {'status': 'error', 'code': 'backend_unavailable'}
        print(json.dumps(result))
        return int(result['status'] == 'error')
    if arguments.operation == 'initial-admin':
        import django
        django.setup()
        from django.core.management import call_command
        from django.core.management.base import CommandError
        try:
            call_command('provision_initial_admin')
        except (CommandError, EOFError, KeyboardInterrupt):
            print('Initial administrator was not created; check inputs and retry.', file=sys.stderr)
            return 1
        return 0
    try:
        # Imports or third-party app startup must not corrupt the single JSON result.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = inspect_backend()
    except Exception:
        result = {'schema': 'error', 'admin_exists': None, 'diagnostics': [{'name': 'backend', 'status': 'error', 'detail': 'Backend configuration or dependency inspection failed; details withheld.'}]}
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
