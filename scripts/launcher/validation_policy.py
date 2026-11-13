"""Small shared admission boundary for managed and developer validation."""
from .model import LauncherError


def require_validation_policy(value='managed', *, profile='dev', source_selection=None) -> str:
    """Reject malformed or unsupported requests without echoing untrusted input.

    Internal launcher callers may omit source selection after Manager admission;
    external request boundaries must supply their explicit selection.
    """
    field = 'validation_policy'
    message = None
    if not isinstance(value, str) or value not in {'managed', 'developer'}:
        message = 'Geçerli bir doğrulama politikası seçin.'
    elif value == 'developer' and profile != 'dev':
        message = 'Geliştirici modu yalnız geliştirme profilinde kullanılabilir.'
    elif value == 'developer' and source_selection is not None and source_selection != 'explicit':
        field = 'source_root'
        message = 'Geliştirici modu için düzenlenebilir kaynak dizinini açıkça seçin.'
    if message:
        error = LauncherError(message)
        error.code = 'invalid_validation_policy'
        error.field = field
        raise error
    return value
