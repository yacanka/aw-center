"""Bounded, owner-only persistence for non-secret desktop form inputs."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import json
import os
import re
from pathlib import Path
import tempfile

from scripts.launcher.installation_permissions import (PERMISSION_CHECK_LABELS, require_private,
                                                      require_unlinked, secure_path)
from scripts.launcher.installation_state import private_directory
from scripts.launcher.model import LauncherError
from .view_model import DEFAULT_VALUES, FormError, _https

_LIMIT = 128 * 1024
_STAGES = {
    'location': 'Kullanıcı kayıt konumunu belirleme',
    'path': 'Bağlantı / reparse noktası denetimi',
    'directory': 'Kullanıcıya özel kayıt klasörünü hazırlama',
    'permissions': 'Dosya sahipliği ve erişim izinlerini doğrulama',
    'read': 'Ayar dosyasını okuma', 'decode': 'Kayıt biçimini doğrulama',
    'encode': 'Form değerlerini hazırlama', 'create': 'Geçici dosya oluşturma',
    'secure': 'Geçici dosyayı kullanıcıya özel koruma',
    'write': 'Geçici dosyaya yazma', 'replace': 'Atomik kayıt değiştirme',
    'cleanup': 'Geçici dosyayı temizleme',
}
_REASONS = {
    'localappdata': ('LOCALAPPDATA geçerli bir mutlak kullanıcı dizini değil.', 'Windows kullanıcı profilinin kullanılabilir olduğunu kontrol edin.'),
    'access_denied': ('Windows veya dosya sistemi erişimi reddetti.', 'Kendi Windows hesabınızla açın; klasörün yazma iznini ve güvenlik yazılımının engellemesini kontrol edin.'),
    'file_locked': ('Ayar dosyası başka bir işlem tarafından kilitlenmiş.', 'Diğer Manager pencerelerini ve dosyayı kullanan programları kapatıp yeniden deneyin.'),
    'disk_full': ('Kayıt diski veya kullanıcı kotası dolu.', 'Kullanıcı diskinizde yer açıp yeniden deneyin.'),
    'read_only': ('Kayıt alanı salt okunur.', 'Windows kullanıcı profilinin yazılabilir yerel bir diskte olduğunu kontrol edin.'),
    'missing_path': ('Kayıt dizini işlem sırasında bulunamadı.', 'Kullanıcı profilinin erişilebilir olduğunu kontrol edip Manager’ı yeniden açın.'),
    'security_check': ('Yol, sahiplik veya yalnız kullanıcıya açık izinler doğrulanamadı.', 'Kayıt alanının size ait ve bağlantı/junction içermeyen yerel bir dizin olduğunu kontrol edin.'),
    'invalid_format': ('Kayıt dosyasının JSON biçimi veya sürümü geçersiz.', 'Formu yeniden doldurun; normal kapanışta yeni kayıt oluşturulur.'),
    'too_large': ('Form kaydı 128 KiB sınırını aşıyor.', 'Gereksiz uzun alanları kısaltıp yeniden deneyin.'),
    'io_error': ('Dosya sistemi işlemi tamamlanamadı.', 'Aşağıdaki aşama ve sistem hata koduyla disk / kullanıcı profili erişimini kontrol edin.'),
}


class PreferencesError(LauncherError):
    """Safe diagnostics: fixed stage/reason and numeric OS codes, never raw paths."""

    def __init__(self, stage, code, *, legacy=False, system_error=None):
        super().__init__('Manager form ayarları işlemi tamamlanamadı.')
        self.stage, self.code, self.legacy = stage, code, legacy
        self.winerror = getattr(system_error, 'winerror', None)
        self.errno = getattr(system_error, 'errno', None)
        self.permission_code = getattr(system_error, 'permission_code', None)
        self.cleanup_failed = False

    def message(self, action):
        heading = ('Manager form ayarları kaydedilemedi. Son değerleri sonraki açılışta yeniden girmeniz gerekebilir.'
                   if action == 'save' else 'Kayıtlı form ayarları okunamadı; varsayılan alanlar açıldı.')
        location = (r'%LOCALAPPDATA%\AWCenter\config\manager.json' if self.legacy else
                    r'%LOCALAPPDATA%\AWCenterManager\manager.json')
        reason, remedy = _REASONS.get(self.code, _REASONS['io_error'])
        lines = [heading, 'Aşama: ' + _STAGES.get(self.stage, _STAGES['location']),
                 'Konum: ' + location, 'Neden: ' + reason,
                 'Hata kodu: preferences_' + (self.code if self.code in _REASONS else 'io_error')]
        for label, value in (('WinError', self.winerror), ('errno', self.errno)):
            if type(value) is int and value > 0:
                lines.append(f'{label} {value}')
        if self.permission_code in PERMISSION_CHECK_LABELS:
            lines.append(f'İzin kontrolü ({self.permission_code}): {PERMISSION_CHECK_LABELS[self.permission_code]}')
        if self.cleanup_failed:
            lines.append('Geçici kayıt dosyasının temizlenmesi de tamamlanamadı.')
        return '\n'.join([*lines, 'Çözüm: ' + remedy])


def _storage_error(stage, error, *, legacy=False):
    winerror, number = getattr(error, 'winerror', None), getattr(error, 'errno', None)
    code = ({32: 'file_locked', 33: 'file_locked', 112: 'disk_full', 19: 'read_only',
             5: 'access_denied', 2: 'missing_path', 3: 'missing_path'}.get(winerror) or
            {errno.ENOSPC: 'disk_full', getattr(errno, 'EDQUOT', -1): 'disk_full', errno.EROFS: 'read_only',
             errno.EACCES: 'access_denied', errno.EPERM: 'access_denied',
             errno.ENOENT: 'missing_path'}.get(number) or
            ('security_check' if isinstance(error, LauncherError) else 'io_error'))
    return PreferencesError(stage, code, legacy=legacy, system_error=error)


@contextmanager
def _step(stage, *, legacy=False):
    try:
        yield
    except PreferencesError:
        raise
    except (OSError, LauncherError) as error:
        raise _storage_error(stage, error, legacy=legacy) from None


def preferences_home() -> Path:
    """Separate UI preferences from installation state; never request elevation."""
    local = os.environ.get('LOCALAPPDATA', '')
    if not local or any(char in local for char in '\0\r\n') or not Path(local).is_absolute():
        raise PreferencesError('location', 'localappdata')
    return Path(local) / 'AWCenterManager'


def _safe_values(values: dict) -> dict:
    result = {}
    for key, default in DEFAULT_VALUES.items():
        value = values.get(key)
        # Migration authorization is specific to one operation, never a preference.
        if key in {'migrate', 'bundle_import'} or type(value) is not type(default):
            continue
        if isinstance(value, str):
            value = value.strip()
            if len(value) > 8192 or any(character in value for character in '\0\r\n'):
                continue
            if value and (key in {'python_index_url', 'npm_registry_url'} or
                          (key == 'repository' and '://' in value)):
                try:
                    _https(value, key)
                except FormError:
                    continue
        if key == 'profile' and value not in {'dev', 'prod'}:
            continue
        if key == 'source_mode' and value not in {'online', 'restricted', 'corporate', 'offline'}:
            continue
        if key == 'migration_policy' and value not in {'automatic', 'confirm'}:
            continue
        if key == 'source_selection' and value not in {'automatic', 'explicit'}:
            continue
        result[key] = value
    return result


def _context_values(values):
    """Only bounded, non-secret preference history is retained for moved media."""
    context = values.get('_media_context')
    if not isinstance(context, str) or not re.fullmatch(r'[0-9a-f]{64}', context):
        return {}
    history = values.get('_contexts', {})
    if not isinstance(history, dict):
        history = {}
    return {'_media_context': context, '_contexts': {
        key: _safe_values(value) for key, value in history.items()
        if isinstance(key, str) and re.fullmatch(r'[0-9a-f]{64}', key) and isinstance(value, dict)}}


def load_preferences(home: Path) -> dict:
    """Read settings without creating profiles or interpreting any saved command."""
    path = home / 'manager.json'
    with _step('path'):
        require_unlinked(path)
        current_exists = path.exists()
    if current_exists:
        return _read_preferences(path, (home, path))
    # Read-only migration: an old installation's permissions are never changed.
    legacy = home.parent / 'AWCenter/config/manager.json'
    with _step('path', legacy=True):
        require_unlinked(legacy)
        if not legacy.exists():
            return {}
    return _read_preferences(legacy, (legacy.parent.parent, legacy.parent, legacy), legacy=True)


def _read_preferences(path, private_paths, *, legacy=False):
    with _step('permissions', legacy=legacy):
        for item in private_paths:
            require_private(item)
    with _step('read', legacy=legacy):
        with path.open('rb') as stream:
            content = stream.read(_LIMIT + 1)
    try:
        if len(content) > _LIMIT:
            raise PreferencesError('decode', 'too_large', legacy=legacy)
        document = json.loads(content)
        if (not isinstance(document, dict) or document.get('version') not in {1, 2} or
                not isinstance(document.get('values'), dict)):
            raise ValueError
        return {**_safe_values(document['values']), **_context_values(document)}
    except (ValueError, UnicodeError, RecursionError):
        raise PreferencesError('decode', 'invalid_format', legacy=legacy) from None


def save_preferences(home: Path, values: dict) -> None:
    """Atomically replace only supported inputs; never read selected file contents."""
    try:
        contexts = _context_values(values)
        content = json.dumps({'version': 2 if contexts else 1, 'values': _safe_values(values), **contexts},
                             ensure_ascii=False).encode('utf-8')
    except UnicodeError:
        raise PreferencesError('encode', 'invalid_format') from None
    if len(content) > _LIMIT:
        raise PreferencesError('encode', 'too_large')
    with _step('directory'):
        directory = private_directory(home)
    destination = directory / 'manager.json'
    with _step('path'):
        require_unlinked(destination)
    with _step('permissions'):
        if destination.exists():
            require_private(destination)
    with _step('create'):
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix='.manager-')
    path = Path(temporary)
    failure = None
    try:
        with _step('write'), os.fdopen(descriptor, 'wb') as stream:
            with _step('secure'):
                secure_path(path)
            stream.write(content)
        with _step('replace'):
            os.replace(path, destination)
    except PreferencesError as error:
        failure = error
        raise
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            if failure is None:
                raise _storage_error('cleanup', error) from None
            failure.cleanup_failed = True
