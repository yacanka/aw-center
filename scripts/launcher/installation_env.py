"""Explicit dotenv imports into an owner-only profile, never source-file writes."""
from __future__ import annotations

from pathlib import Path
import stat

from .installation_permissions import require_unlinked
from .installation_profiles import (
    EnvironmentImportError, _check_inherited, _environment_content, _require_separate, _validate_environment,
    _write_replace, parse_environment, read_profile_environment,
)


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
            raise EnvironmentImportError('env_file_invalid')
        if name == 'prod' and source.resolve().is_relative_to(project.root.resolve()):
            raise EnvironmentImportError('env_source_location_invalid')
        with source.open(encoding='utf-8-sig') as stream:
            content = stream.read(MAX_ENV_BYTES + 1)
        if len(content) > MAX_ENV_BYTES:
            raise EnvironmentImportError('env_file_invalid')
        values = parse_environment(content)
        forbidden = [key for key in values if key in _CONTROL_KEYS or key.startswith(_CONTROL_PREFIXES)]
        if forbidden:
            raise EnvironmentImportError('env_process_setting_forbidden', keys=forbidden)
        return values
    except (OSError, UnicodeError, ValueError):
        raise EnvironmentImportError('env_file_invalid') from None


def merge_selected_environment(profile, current: dict, selected: dict, *, existing: bool) -> dict:
    identity_keys = ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY')
    selected = {key: value for key, value in selected.items() if key not in identity_keys or value.strip()}
    conflicts = [key for key in identity_keys if existing and key in selected and selected[key] != current[key]]
    if conflicts:
        raise EnvironmentImportError('env_identity_conflict', keys=conflicts)
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
        raise EnvironmentImportError('env_import_required')
