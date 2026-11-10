"""Validated first administrator creation shared by terminal and desktop setup.

Provisioning only inserts a new account. Existing accounts are never reset or
promoted, and an existing active administrator makes the operation a no-op.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from users.username_policy import validate_username_format


def initial_admin_exists() -> bool:
    return get_user_model().objects.filter(is_superuser=True, is_active=True).exists()


def validate_initial_admin_username(username: str) -> None:
    """Reject invalid identities and existing accounts before requesting a password."""
    validate_username_format(username)
    if get_user_model().objects.filter(username__iexact=username).exists():
        raise ValidationError('That account already exists; it will not be changed or promoted.')


def create_initial_admin(username: str, password: str) -> bool:
    """Insert the first admin, returning False if one already exists.

    Validation failures and conflicting accounts raise ValidationError. The
    password is validated and hashed in memory; no raw credential is persisted.
    """
    if initial_admin_exists():
        return False
    username = username.strip()
    validate_initial_admin_username(username)
    user = get_user_model()(username=username, is_active=True, is_staff=True, is_superuser=True)
    validate_password(password, user=user)
    try:
        with transaction.atomic():
            if initial_admin_exists():
                return False
            user.set_password(password)
            user.save(force_insert=True)
    except IntegrityError:
        raise ValidationError('The account already exists; no account was changed.') from None
    return True
