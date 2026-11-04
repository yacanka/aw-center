"""Verified Manager media; full bundles include a pinned, isolated toolchain."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile

from scripts.launcher.installation_bundle import _json_object, _verify_inventory, install_inventory
from scripts.launcher.installation_permissions import require_unlinked
from scripts.launcher.model import LauncherError
from .payload import verify_source_payload

MANIFEST = 'manager-manifest.json'


def seal_distribution(directory: Path, *, complete=False) -> dict:
    source = verify_source_payload(directory / 'source')
    manifest = {'format_version': 2, 'target': 'windows-x64', 'python': '3.11',
                'complete': complete, 'source_fingerprint': source['fingerprint'],
                'artifacts': install_inventory(directory, exclude=(MANIFEST,), source_state=True)}
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return verify_distribution(directory)


def verify_distribution(directory: Path) -> dict:
    directory = Path(directory).absolute()
    require_unlinked(directory / MANIFEST)
    manifest = _json_object(directory / MANIFEST)
    if (manifest.get('format_version') not in {1, 2} or manifest.get('target') != 'windows-x64'
            or manifest.get('python') != '3.11'):
        raise LauncherError('Manager dağıtım manifest’i uyumsuz.')
    _verify_inventory(directory, manifest.get('artifacts'), exclude=(MANIFEST,), source_state=True)
    if not (directory / 'AWCenterManager.exe').is_file() or not (directory / '_internal').is_dir():
        raise LauncherError('Manager EXE veya gömülü runtime eksik.')
    source = verify_source_payload(directory / 'source')
    if source['fingerprint'] != manifest.get('source_fingerprint'):
        raise LauncherError('Manager ve dağıtılan kaynak kimlikleri uyuşmuyor.')
    return manifest


def copy_manager(distribution: Path, destination: Path) -> None:
    manifest = verify_distribution(distribution)
    if verify_source_payload(destination / 'source')['fingerprint'] != manifest['source_fingerprint']:
        raise LauncherError('Aynı sürümden üretilmiş Windows Manager paketi seçin.')
    for name in ('AWCenterManager.exe', '_internal'):
        target = destination / name
        if target.exists():
            raise LauncherError('Manager çıktı dosyaları mevcut; üzerine yazılmadı.')
        if name == '_internal':
            shutil.copytree(distribution / name, target)
        else:
            shutil.copy2(distribution / name, target)
    # Validate copied bytes, not just the source before copying.
    expected = [entry for entry in manifest['artifacts']
                if entry['path'] == 'AWCenterManager.exe' or entry['path'].startswith('_internal/')]
    from scripts.launcher.offline_manifest import file_sha256
    for entry in expected:
        path = destination / entry['path']
        if path.stat().st_size != entry['size'] or file_sha256(path) != entry['sha256']:
            raise LauncherError('Manager kopyası doğrulanamadı.')


def prepare_full_manager(project, output, settings, distribution, *, assets=None, feature_catalog=None):
    """Never borrow producer runtimes or mutate an active application's tools."""
    from scripts.launcher.installation import require_windows
    from scripts.launcher.installation_bundle import prepare_install_bundle
    from scripts.launcher.installation_state import process_environment
    from scripts.launcher.toolchain import ensure_toolchain
    require_windows()
    distribution = Path(distribution).absolute()
    verify_distribution(distribution)
    settings = replace(settings, runtime_dirs=(*settings.runtime_dirs, distribution))
    settings.report('Tam paket için sabitlenmiş araçlar ayrı hazırlık alanında kuruluyor')
    with tempfile.TemporaryDirectory(prefix='awcenter-full-manager-') as temporary:
        tools = ensure_toolchain(Path(temporary).resolve() / 'tools', settings)
        with process_environment(tools):
            return prepare_install_bundle(project, output, settings, assets=assets,
                feature_catalog=feature_catalog, manager_distribution=distribution)
