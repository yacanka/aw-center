"""Owner-scoped build evidence for Manager's verified immutable production release."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .installation_bundle import _json_object, _relative_path
from .installation_dependencies import _preserve_package_tree
from .installation_permissions import require_private, require_unlinked, secure_path
from .installation_state import private_directory
from .model import LauncherError
from .offline_manifest import file_sha256
from .process import check_cancelled


class FrontendBuildError(LauncherError):
    code = 'frontend_build_invalid'
    remedy = ('Üretim sürümündeki frontend/dist ve .runtime/frontend-build dizinlerini '
              'yedek bir konuma taşıyıp AW Center’ı aç düğmesine basın.')

    def __init__(self):
        super().__init__('Üretim arayüzünün derleme kaydı veya çıktı dosyaları güvenle doğrulanamadı.')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _inputs(project, profile, tools):
    from .installation_sources import load_catalog
    from .toolchain import _environment
    catalog = load_catalog()
    if tools is None:
        node = profile.get('node_executable')
        tools = _environment(Path(profile['installation_home']), catalog,
                             node_executable=Path(node) if node else None)
    node = Path(tools['AWCENTER_MANAGED_NODE'])
    npm = Path(tools['AWCENTER_MANAGED_NPM_CLI'])
    manifest = project.root / 'manager-source-manifest.json'
    require_unlinked(manifest)
    # The Manager validates this release's entire source manifest on selection.
    # Keep site-specific build settings and tool paths out of the receipt.
    build_env = {k: v for k, v in {**os.environ, **tools}.items()
                 if k.startswith('VITE_') or k in ('NODE_ENV', 'BROWSERSLIST', 'BROWSERSLIST_ENV')}
    return _digest([file_sha256(manifest), str(node), file_sha256(node), str(npm), file_sha256(npm),
                    file_sha256(npm.parent.parent / 'package.json'), catalog['node'].sha256,
                    catalog['npm'].sha256, build_env])


def _output(dist):
    """Include every regular output, including route chunks loaded after boot."""
    require_unlinked(dist)
    if not dist.exists():
        return None
    if not dist.is_dir():
        raise FrontendBuildError()
    files = {}
    pending = [dist]
    while pending:
        for path in pending.pop().iterdir():
            check_cancelled()
            require_unlinked(path)
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                pending.append(path)
            elif stat.S_ISREG(mode):
                relative = path.relative_to(dist).as_posix()
                _relative_path(relative)
                files[relative] = file_sha256(path)
            else:
                raise FrontendBuildError()
    return _digest(files) if 'index.html' in files else None


def _receipt(project):
    return project.root / '.runtime' / 'frontend-build' / 'receipt.json'


def build_is_current(project, profile, tools=None):
    path = _receipt(project)
    require_unlinked(path)
    if not path.exists():
        return False
    require_private(path.parent)
    require_private(path)
    try:
        saved = _json_object(path, limit=512)
        if (set(saved) != {'version', 'inputs', 'output'} or type(saved['version']) is not int or
                saved['version'] != 1 or any(not isinstance(saved[k], str) or
                                             not re.fullmatch('[0-9a-f]{64}', saved[k])
                                             for k in ('inputs', 'output'))):
            raise ValueError
    except (LauncherError, ValueError):
        raise FrontendBuildError() from None
    return saved['output'] == _output(project.frontend / 'dist') and saved['inputs'] == _inputs(project, profile, tools)


def _record(project, inputs, output):
    path = _receipt(project)
    private_directory(path.parent)
    require_unlinked(path)
    if path.exists():
        require_private(path)
    data = json.dumps({'version': 1, 'inputs': inputs, 'output': output}).encode()
    descriptor, filename = tempfile.mkstemp(dir=path.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            secure_path(temporary, file_descriptor=stream.fileno())
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_build(project, profile, tools, build, deploy, report):
    """Publish evidence only after a clean build and the mandatory deployment gates."""
    if build_is_current(project, profile, tools):
        report('Doğrulanmış üretim arayüzü yeniden kullanılıyor')
        report('Üretim dağıtım kontrolleri çalıştırılıyor')
        deploy()
        return
    inputs = _inputs(project, profile, tools)
    dist = project.frontend / 'dist'
    require_unlinked(dist)
    if dist.exists():
        _output(dist)  # Authenticate path types even for an older receipt-free release.
        _preserve_package_tree(project, dist, 'frontend-build-backups')
        report('Önceki arayüz çıktısı .runtime/frontend-build-backups altında korundu')
    report('Üretim arayüzü derleniyor')
    build()
    report('Üretim dağıtım kontrolleri çalıştırılıyor')
    deploy()
    output = _output(dist)
    if output is None:
        raise FrontendBuildError()
    _record(project, inputs, output)
