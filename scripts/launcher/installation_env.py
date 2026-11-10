"""Explicit dotenv imports into an owner-only profile, never source-file writes."""
from __future__ import annotations

from pathlib import Path
import stat

from .installation_permissions import require_unlinked
from .installation_profiles import (
    _check_inherited, _environment_content, _require_separate, _validate_environment,
    _write_replace, parse_environment, read_profile_environment,
)
from .model import LauncherError

MAX_ENV_BYTES = 128 * 1024
_CONTROL_KEYS = {'PATH', 'PATHEXT', 'HOME', 'LOCALAPPDATA', 'TEMP', 'TMP', 'COMSPEC',
                 'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'USERPROFILE', 'APPDATA',
                 'ENV', 'BASH_ENV', 'AWCENTER_ENV_FILE', 'DJANGO_SETTINGS_MODULE',
                 'DJANGO_ALLOW_ASYNC_UNSAFE', 'AWCENTER_OFFLINE_DIR', 'AWCENTER_PACKAGE_REPOSITORY',
                 'PYLAUNCHER_ALLOW_INSTALL', 'PYTHON_MANAGER_AUTOMATIC_INSTALL'}
_CONTROL_PREFIXES = ('PYTHON', 'PIP_', 'NPM_CONFIG_', 'NODE_', 'LD_', 'DYLD_', 'AWCENTER_MANAGED_')


def read_selected_environment(project, name: str, source: Path) -> dict[str, str]:
    """Read a selected config source; only its private runtime copy is consumed.

    Source permissions/content are never modified. Sources may be ordinary user
    config files; all consumed runtime secrets still use the private profile ACL.
    """
    source = Path(source).absolute()
    try:
        require_unlinked(source)
        info = source.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ENV_BYTES:
            raise LauncherError('Seçilen .env normal ve boyut sınırı içinde bir dosya olmalıdır.')
        if name == 'prod' and source.resolve().is_relative_to(project.root.resolve()):
            raise LauncherError('Production için seçilen .env kaynak ağacının dışında olmalıdır.')
        with source.open(encoding='utf-8-sig') as stream:
            content = stream.read(MAX_ENV_BYTES + 1)
        if len(content) > MAX_ENV_BYTES:
            raise LauncherError('Seçilen .env boyut sınırını aşıyor.')
        values = parse_environment(content)
        if any(any(ord(char) < 32 or ord(char) == 127 for char in value) for value in values.values()):
            raise LauncherError('Seçilen .env değerleri kontrol karakteri içeremez; değerler gizlendi.')
        if any(key in _CONTROL_KEYS or key.startswith(_CONTROL_PREFIXES) for key in values):
            raise LauncherError('Seçilen .env süreç başlatma veya başka env dosyasına yönlendirme ayarları içeremez.')
        return values
    except (OSError, UnicodeError, ValueError):
        raise LauncherError('Seçilen .env okunamadı veya biçimi geçersiz; değerler gizlendi.') from None


def merge_selected_environment(profile, current: dict, selected: dict, *, existing: bool) -> dict:
    if existing and any(key in selected and selected[key] != current[key]
                        for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY')):
        raise LauncherError('Seçilen .env mevcut profilin anahtarlarını değiştiremez; değerler gizlendi.')
    merged = {**current, **selected}
    _validate_environment(profile, merged)
    _require_separate(Path(profile['installation_home']), profile['name'], merged, profile['source_root'])
    _check_inherited(merged, profile['env_file'])
    return merged


def import_selected_environment(profile, selected: dict) -> None:
    """Atomic single-file replacement; caller holds the installation lock."""
    current = read_profile_environment(profile)
    merged = merge_selected_environment(profile, current, selected, existing=True)
    if merged != current:
        _write_replace(Path(profile['env_file']), _environment_content(merged))


def check_selected_environment(project, profile, source: Path) -> None:
    """Read-only Start/Doctor never silently import changed configuration."""
    selected = read_selected_environment(project, profile['name'], source)
    current = read_profile_environment(profile)
    merged = merge_selected_environment(profile, current, selected, existing=True)
    if merged != current:
        raise LauncherError('Seçilen .env profil ayarlarından farklı; uygulamak için Kur ve başlat kullanın.')
