"""Account email policy backed by database-maintained identity reservations."""
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Value
from django.db.models.functions import Lower, Trim


EMAIL_UNAVAILABLE = 'This email address is unavailable.'


def normalize_email_identity(value):
    """Normalize a new identity with exactly the database guard's rules."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT lower(trim(%s))', [value])
        return cursor.fetchone()[0]


def accounts_for_email(value):
    """Use the guard's database collation/LOWER rules, including for recovery.

    SQLite LOWER handles ASCII case; PostgreSQL uses its configured collation.
    Do not substitute Python casefold: it can disagree with either database.
    """
    return get_user_model().objects.alias(
        email_identity=Lower(Trim('email')),
    ).filter(email_identity=Lower(Trim(Value(value))))


def validate_email_identity(value, *, user=None):
    """Keep legacy identities editable; the database arbitrates racing writes."""
    if not value or not value.strip():
        return value
    accounts = accounts_for_email(value)
    if user is not None and user.pk is not None:
        if accounts.filter(pk=user.pk).exists():
            return value
        accounts = accounts.exclude(pk=user.pk)
    if accounts.exists():
        raise ValidationError(EMAIL_UNAVAILABLE)
    return value


def is_email_identity_conflict(error):
    cause = error.__cause__
    constraint = getattr(getattr(cause, 'diag', None), 'constraint_name', '')
    return constraint == 'users_email_identity_pkey' or str(error) == 'users_email_identity_conflict' or (
        'UNIQUE constraint failed: users_email_identity.email' in str(error)
    )


@contextmanager
def email_identity_write():
    """Rollback a losing write before exposing a bounded field error."""
    from rest_framework.exceptions import ValidationError as APIValidationError

    try:
        with transaction.atomic():
            yield
    except IntegrityError as error:
        if not is_email_identity_conflict(error):
            raise
        raise APIValidationError({'email': EMAIL_UNAVAILABLE}) from error
