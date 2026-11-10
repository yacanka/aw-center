"""Bounded, read-only feature inventory and explicit approved asset import.

Presence is reported as configured. Licensed software and private integration
connectivity require operator acceptance; inspection never opens Office or DOORS.
"""
from __future__ import annotations

import json
from dataclasses import asdict
import re
import os
from pathlib import Path
import shutil
import tempfile

from .installation_bundle import (ASSET_MANIFEST, _json_object, _relative_path,
                                  _safe_path, _verify_inventory, install_inventory,
                                  verify_asset_source)
from .installation_permissions import require_private, require_unlinked, secure_path
from .installation_profiles import installation_home, read_profile_environment
from .installation_sources import (Artifact, _validate_artifact, fetch_artifact,
                                   load_catalog, safe_extract)
from .model import LauncherError
from .offline_manifest import file_sha256

MODEL_KEYS = {
    'opus-mt-tr-en': 'WORD_TRANSLATION_TR_EN_MODEL',
    'opus-mt-en-tr': 'WORD_TRANSLATION_EN_TR_MODEL',
    'paraphrase-multilingual': 'WORD_ANALYZER_BI_MODEL',
    'ms-marco-cross-encoder': 'WORD_ANALYZER_CROSS_MODEL',
}
PRIVATE_KEYS = ('PROJECT_CONFIGURATION_FILE', 'DDF_ASSESSMENT_POLICY_FILE', 'GOKBEY_DCC_POLICY_FILE')
TOOL_KEYS = {'ffmpeg': ('FFMPEG_EXECUTABLE', 'ffmpeg'), 'ffprobe': ('', 'ffprobe'),
             'soffice': ('SOFFICE_BIN', 'soffice'), 'pdftoppm': ('PDFTOPPM_BIN', 'pdftoppm')}
OPTIONAL_ARTIFACTS = {'ffmpeg': ('ffmpeg', 'ffprobe'), 'libreoffice': ('soffice',),
                      'poppler': ('pdftoppm',)}


def read_feature_catalog(path: Path, *, require_owner: bool = True) -> dict[str, Artifact]:
    """Read explicit operator-approved pins, never a repository-supplied manifest.

    This opt-in supports portable ffmpeg, LibreOffice and Poppler archives only.
    It cannot authorize installer commands, Office, DOORS or credential downloads.
    """
    path = Path(path).absolute()
    require_unlinked(path)
    if require_owner:
        require_private(path)
        require_private(path.parent)
    document = _json_object(path, limit=64 * 1024)
    entries = document.get('artifacts')
    if set(document) != {'format_version', 'artifacts'} or document['format_version'] != 1 or not isinstance(entries, list):
        raise LauncherError('approved optional feature catalog is invalid')
    result = {}
    fields = {'name', 'version', 'filename', 'url', 'sha256', 'archive', 'executable'}
    expected = {'ffmpeg': 'ffmpeg.exe', 'libreoffice': 'soffice.exe', 'poppler': 'pdftoppm.exe'}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != fields or any(not isinstance(value, str) for value in entry.values()):
            raise LauncherError('approved optional feature artifact is invalid')
        name = entry['name']
        if name not in OPTIONAL_ARTIFACTS or name in result or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', entry['version']) is None:
            raise LauncherError('unsupported or duplicate optional feature artifact')
        artifact = Artifact(**entry)
        _validate_artifact(artifact)
        executable = _relative_path(artifact.executable)
        if executable.name.lower() != expected[name]:
            raise LauncherError('optional feature must identify the expected portable executable')
        result[name] = artifact
    return result


def _catalog_for_home(home: Path) -> dict[str, Artifact]:
    catalog = load_catalog()
    path = home / 'config/features.catalog.json'
    if path.exists():
        catalog.update(read_feature_catalog(path))
    return catalog


def _secure_directory(path: Path) -> None:
    require_unlinked(path)
    if path.exists():
        require_private(path)
        return
    path.mkdir(parents=True, exist_ok=False)
    secure_path(path)


def _persist_feature_catalog(home: Path, catalog: dict[str, Artifact]) -> None:
    _secure_directory(home)
    _secure_directory(home / 'config')
    destination = home / 'config/features.catalog.json'
    require_unlinked(destination)
    if destination.exists():
        require_private(destination)
    payload = {'format_version': 1, 'artifacts': [asdict(artifact) for artifact in catalog.values()]}
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            secure_path(temporary)
            json.dump(payload, output, sort_keys=True)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _row(name: str, status: str, detail: str) -> dict:
    return {'name': name, 'status': status, 'detail': detail[:400]}


def _home(profile) -> Path:
    return Path(profile['installation_home']) if profile.get('installation_home') else installation_home()


def _external_home(project, profile) -> Path:
    home = _home(profile).absolute()
    require_unlinked(home)
    if home.resolve().is_relative_to(project.root.resolve()):
        raise LauncherError('managed assets and tools must be outside the source tree')
    return home


def _configured_path(value: str, project) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else project.backend / path


def _tool_path(name: str, values: dict, extra_path: str = '') -> str | None:
    key, fallback = TOOL_KEYS[name]
    configured = values.get(key, '') if key else ''
    return shutil.which(configured or fallback, path=extra_path or None)


def _asset_directory(project, profile, values) -> Path:
    return _home(profile) / 'assets' / 'sets' / _relative_path(profile.get('asset_set', 'default'))


def _model_present(path: Path) -> bool:
    """Bounded presence check; multi-GB model hashes are verified during import."""
    try:
        require_unlinked(path)
        with os.scandir(path) as entries:
            for index, entry in enumerate(entries):
                if index >= 512:
                    return False
                if entry.is_file(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_size:
                    return True
    except (LauncherError, OSError):
        return False
    return False


def _approved_templates(assets: Path, templates: Path) -> bool:
    try:
        require_unlinked(templates)
        if templates.resolve() != (assets / 'document-templates').resolve():
            return False
        manifest = _json_object(_safe_path(assets, assets / ASSET_MANIFEST))
        entries = manifest.get('artifacts')
        if manifest.get('format_version') != 1 or manifest.get('asset_set') != assets.name or not isinstance(entries, list):
            return False
        approved = []
        for item in entries:
            if not isinstance(item, dict):
                return False
            relative = _relative_path(item.get('path'))
            if relative.parts[0] != 'document-templates':
                continue
            if set(item) != {'path', 'size', 'sha256'} or relative.suffix.lower() != '.docx':
                return False
            path = _safe_path(assets, assets / relative)
            if path.stat().st_size != item['size'] or file_sha256(path) != item['sha256']:
                return False
            approved.append(path)
        return bool(approved)
    except (LauncherError, OSError, KeyError, TypeError):
        return False


def _model_rows(project, profile, values: dict) -> list[dict]:
    assets = _asset_directory(project, profile, values)
    model_root = _configured_path(values['MODEL_RUNTIME_DIR'], project) if values.get('MODEL_RUNTIME_DIR') else assets / 'ai-models'
    rows = []
    for name, key in MODEL_KEYS.items():
        path = _configured_path(values[key], project) if values.get(key) else model_root / name
        present = _model_present(path)
        rows.append(_row(name, 'configured' if present else 'missing',
                         'Local model files present; inference and current integrity not verified.' if present else
                         'Supply the approved local model directory; no model download is assumed.'))
    templates = _configured_path(values['CUSTOM_TEMPLATE_DIR'], project) if values.get('CUSTOM_TEMPLATE_DIR') else assets / 'document-templates'
    approved = _approved_templates(assets, templates)
    rows.append(_row('document-templates', 'configured' if approved else 'missing',
                     'Approved DOCX template asset set verified; rendering not verified.' if approved else
                     'Supply DOCX templates with an approved asset-manifest.json and immutable SHA-256 hashes.'))
    return rows


def _private_row(key: str, value: str, project) -> dict:
    if not value:
        return _row(key, 'missing', 'Supply the approved private JSON file outside source and artifact storage.')
    try:
        path = _configured_path(value, project)
        if not path.is_absolute() or path.resolve().is_relative_to(project.root.resolve()):
            raise LauncherError('private file must be external')
        require_private(path)
        require_private(path.parent)
        data = _json_object(path, limit=64 * 1024)
        valid = data.get('schema_version') == 1
    except (LauncherError, OSError):
        valid = False
    return _row(key, 'configured' if valid else 'missing',
                'Private JSON present with owner-only access; application schema not verified.' if valid else
                'Private JSON missing, invalid or not owner-restricted; values withheld.')


def _com_row(label: str, progid: str) -> dict:
    if os.name != 'nt':
        return _row(label, 'missing', 'Requires licensed Windows desktop Office and COM registration.')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + '\\CLSID'):
            pass
    except OSError:
        return _row(label, 'missing', 'Office COM registration missing; install licensed Office through the approved channel.')
    return _row(label, 'configured', 'Office COM registered; license, Python COM adapter and desktop automation not verified.')


def _remote_rows(values: dict) -> list[dict]:
    definitions = (
        ('JIRA', 'JIRA_ENABLED', ('JIRA_URL', 'JIRA_SESSION_ENCRYPTION_KEY')),
        ('Teamcenter', 'TEAMCENTER_ENABLED', ('TEAMCENTER_BASE_URL',)),
        ('DocProof', 'DOCPROOF_ENABLED', ('DOCPROOF_URL',)),
        ('Numarator', 'NUMARATOR_ENABLED', ('NUMARATOR_BASE_URL', 'NUMARATOR_API_KEY')),
        ('AI API', '', ('AI_API_URL', 'AI_API_MODEL_ID', 'AI_API_TOKEN', 'AI_API_ALLOWED_HOSTS')),
    )
    rows = []
    for name, enabled, required in definitions:
        active = not enabled or values.get(enabled, '').casefold() in {'1', 'true', 'yes', 'on'}
        configured = active and all(values.get(key) for key in required)
        rows.append(_row(name, 'configured' if configured else 'missing',
                         'Configured; remote connectivity, authorization and corporate TLS not verified.' if configured else
                         'Supply approved endpoint, trust and credential configuration; integration remains unverified.'))
    mail = values.get('AWCENTER_MAIL_TRANSPORT') == 'django' and bool(values.get('EMAIL_HOST'))
    rows.append(_row('SMTP', 'configured' if mail else 'missing',
                     'Configured; notification-worker delivery not verified.' if mail else
                     'Configure approved SMTP transport and notification-worker-only credentials.'))
    return rows


def inspect_features(project, profile) -> list[dict]:
    """Inspect configuration without downloading, starting software or writing files."""
    values = read_profile_environment(profile)
    overrides = feature_environment(project, profile)
    rows = []
    for name in TOOL_KEYS:
        present = _tool_path(name, values, overrides.get('PATH', ''))
        rows.append(_row(name, 'configured' if present else 'missing',
                         'Executable available; conversion runtime not verified.' if present else
                         'Executable missing; use a reviewed optional tool artifact or approved local installation.'))
    rows.extend(_model_rows(project, profile, values))
    executable = values.get('DOORS_EXECUTABLE', '')
    doors = bool(executable and shutil.which(executable)) and bool(values.get('DOORS_DATABASE'))
    rows.append(_row('DOORS', 'configured' if doors else 'missing',
                     'DOORS executable and database configured; license, connection and worker execution not verified.' if doors else
                     'Requires licensed DOORS client, executable and database configuration; no automatic license installation.'))
    rows.extend((_com_row('Word COM', 'Word.Application'),
                 _com_row('Outlook COM', 'Outlook.Application'),
                 _com_row('PowerPoint COM', 'PowerPoint.Application')))
    rows.extend(_private_row(key, values.get(key, ''), project) for key in PRIVATE_KEYS)
    rows.extend(_remote_rows(values))
    return rows


def import_asset_set(source: Path, home: Path) -> Path:
    """Import one hash-verified set atomically; existing immutable sets never change."""
    source = Path(source).absolute()
    manifest = verify_asset_source(source)  # No home mutation before full verification.
    home = Path(home).absolute()
    require_unlinked(home)
    destination = home / 'assets' / 'sets' / manifest['asset_set']
    require_unlinked(destination)
    if destination.exists():
        existing = verify_asset_source(destination)
        if existing != manifest:
            raise LauncherError('existing immutable asset set differs; choose a new asset-set identifier')
        return destination
    parent = destination.parent
    for directory in (home, home / 'assets', parent):
        _secure_directory(directory)
    with tempfile.TemporaryDirectory(prefix='.asset-import-', dir=parent) as temporary:
        staging = Path(temporary) / 'set'
        shutil.copytree(source, staging)
        verify_asset_source(staging)
        for current, directories, files in os.walk(staging):
            secure_path(Path(current))
            for name in files:
                secure_path(Path(current) / name)
        staging.rename(destination)
    return destination


def _installed_tool(home: Path, name: str, artifact) -> Path | None:
    destination = home / 'tools' / f'{name}-{artifact.version}'
    if not destination.is_dir():
        return None
    try:
        _safe_path(destination, destination / 'tool-manifest.json')
        manifest = _json_object(destination / 'tool-manifest.json')
        if manifest.get('artifact_sha256') != artifact.sha256:
            return None
        _verify_inventory(destination, manifest.get('artifacts'), exclude=('tool-manifest.json',))
        path = destination / _relative_path(artifact.executable)
        _safe_path(destination, path)
        return path if path.is_file() else None
    except LauncherError:
        return None


def feature_environment(project, profile) -> dict[str, str]:
    """Return process-local paths to verified managed optional tools, never global PATH."""
    home = _home(profile)
    if not (home / 'tools').exists():
        return {}
    catalog = _catalog_for_home(home)
    paths = []
    overrides = {}
    for name in OPTIONAL_ARTIFACTS:
        artifact = catalog.get(name)
        path = _installed_tool(home, name, artifact) if artifact else None
        if path:
            paths.append(str(path.parent))
            if name == 'ffmpeg':
                overrides['FFMPEG_EXECUTABLE'] = str(path)
            if name == 'libreoffice':
                overrides['SOFFICE_BIN'] = str(path)
            if name == 'poppler':
                overrides['PDFTOPPM_BIN'] = str(path)
    if paths:
        overrides['PATH'] = os.pathsep.join([*paths, os.environ.get('PATH', '')])
    return overrides


def _install_tool(home: Path, name: str, artifact, settings) -> None:
    destination = home / 'tools' / f'{name}-{artifact.version}'
    require_unlinked(destination)
    if destination.exists():
        if _installed_tool(home, name, artifact) is None:
            raise LauncherError('existing managed optional tool is invalid; it was not overwritten')
        return
    for directory in (home, home / 'cache', home / 'cache/optional-tools'):
        _secure_directory(directory)
    archive = fetch_artifact(artifact, home / 'cache' / 'optional-tools', settings)
    _secure_directory(home)
    _secure_directory(destination.parent)
    with tempfile.TemporaryDirectory(prefix='.optional-tool-', dir=destination.parent) as temporary:
        staging = Path(temporary) / 'tool'
        safe_extract(archive, staging, artifact.archive)
        path = staging / _relative_path(artifact.executable)
        if not path.is_file():
            raise LauncherError('reviewed optional tool executable is absent')
        manifest = {'artifact_sha256': artifact.sha256, 'artifacts': install_inventory(staging)}
        (staging / 'tool-manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n', encoding='utf-8')
        for current, directories, files in os.walk(staging):
            secure_path(Path(current))
            for filename in files:
                secure_path(Path(current) / filename)
        staging.rename(destination)


def install_features(project, profile, settings, *, assets=None, feature_catalog=None) -> list[dict]:
    """Attempt reviewed optional tools, import explicit assets, then report every gap.

    No Office, DOORS, model or private configuration download is invented. Artifact
    manifests from mirrors cannot authorize execution; only load_catalog can.
    """
    home = _external_home(project, profile)
    approved_catalog = read_feature_catalog(Path(feature_catalog)) if feature_catalog is not None else None
    if assets is not None:
        manifest = verify_asset_source(Path(assets))
        if manifest['asset_set'] != profile.get('asset_set'):
            raise LauncherError('approved asset-set identifier does not match the selected profile')
        import_asset_set(Path(assets), home)
    if approved_catalog is not None:
        _persist_feature_catalog(home, approved_catalog)
    catalog = _catalog_for_home(home)
    failures = []
    for name in OPTIONAL_ARTIFACTS:
        if name not in catalog:
            continue
        try:
            _install_tool(home, name, catalog[name], settings)
        except (LauncherError, OSError):
            failures.append(_row(name + ' installation', 'missing',
                                 'Reviewed optional tool installation failed; existing tools and business state were preserved.'))
    return [*inspect_features(project, profile), *failures]
