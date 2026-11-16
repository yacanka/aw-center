"""Small shared admission boundary for managed and developer validation."""
from .model import LauncherError


def require_validation_policy(value='managed', *, profile='dev', source_selection=None) -> str:
    """Reject malformed or unsupported requests without echoing untrusted input.

    Developer validation is an explicit policy choice for dev, independent of
    whether the source path was detected automatically or selected manually.
    """
    field = 'validation_policy'
    message = None
    if not isinstance(value, str) or value not in {'managed', 'developer'}:
        message = 'Geçerli bir doğrulama politikası seçin.'
    elif value == 'developer' and profile != 'dev':
        message = 'Geliştirici modu yalnız geliştirme profilinde kullanılabilir.'
    if message:
        error = LauncherError(message)
        error.code = 'invalid_validation_policy'
        error.field = field
        raise error
    return value
