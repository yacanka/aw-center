"""Construct pre-guard legacy fixtures in disposable test databases only."""
from importlib import import_module

from django.db import connection


def set_legacy_email(user, email):
    """Reproduce a pre-migration row, then rebuild the exact migration guard."""
    migration = import_module('users.migrations.0002_email_identity_guard')
    editor = connection.schema_editor(atomic=False)
    migration.uninstall_guard(None, editor)
    try:
        user.email = email
        user.save(update_fields=['email'])
    finally:
        editor.execute('DELETE FROM users_email_identity')
        migration.install_guard(None, editor)
