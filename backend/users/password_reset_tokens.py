"""Stable password-reset tokens and non-recoverable account-state fingerprints."""

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import salted_hmac


token_generator = PasswordResetTokenGenerator()


def current_token_timestamp() -> int:
    """Capture Django's password-reset epoch once so retries render one stable link."""

    return token_generator._num_seconds(token_generator._now())


def make_token_at(user, timestamp: int) -> str:
    """Recreate a token for a persisted timestamp without storing the token itself."""

    return token_generator._make_token_with_timestamp(
        user,
        int(timestamp),
        token_generator.secret,
    )


def account_state_digest(user) -> str:
    """HMAC the user state that must remain unchanged until delivery."""

    last_login = user.last_login
    if last_login is not None:
        last_login = last_login.replace(microsecond=0, tzinfo=None)
    state = "\x1f".join(
        (
            str(user.pk),
            str(user.password),
            str(last_login or ""),
            str(user.email or "").casefold(),
            "1" if user.is_active else "0",
        )
    )
    return salted_hmac(
        "users.password-reset-delivery-state",
        state,
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()
