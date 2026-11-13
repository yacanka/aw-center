"""User-scoped, verified Windows toolchains with process-local environment."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import tarfile
import zipfile
from pathlib import Path

from .installation_sources import Artifact, SourceSettings, _digest, _no_symlink, _safe_member, _verify as verify_artifact, fetch_artifact, load_catalog, safe_extract
from .installation_state import private_directory
from .model import LauncherError
from .process import OperationCancelled, controlled_run

RECEIPT = ".awcenter-tool.json"
# Archive SHA-256 -> SHA-256 of its canonical path/content inventory. Reproduce
# from verified archives with BootstrapContractTests.test_installed_tree_pins_match_catalog_verified_archives.
INVENTORY_PINS = {
    "75cb501dc11c7b55c6b447c58e4910bce5b1f609f1017328b4f3a858dfaf5428":
        "359d287d0c4352bf6a4c1c7154fa8e779b07eb4cc45a17aa7d96944d9dad69bf",
    "cbc74b5e0982c9dbb41525fd8fb5dcd32fbee237863f7829072f4639a1ce5f20":
        "b0a41bd146ad8cbe67c3ef0b7d1be968531a32ff01fed3d5dc13cf703312f8dd",
    "4bfba8a0c823024d1926ec9d97a37a00eb60fd2adf44b3d34a686fc32e8f51e4":
        "5bf9ac7cebac92c55dd72de52239081816e997e344e565175187ee18de9c5cd5",
}
MANAGED_RUNTIME_ENVIRONMENT = {
    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
    "PYTHONHOME": "", "PYTHONPATH": "", "PYTHONSTARTUP": "", "PYTHONUSERBASE": "",
    "NODE_OPTIONS": "", "NODE_PATH": "", "NODE_TLS_REJECT_UNAUTHORIZED": "1",
}


class RuntimeValidationError(LauncherError):
    """Fixed runtime/version failure details without subprocess output or paths."""

    def __init__(self, reason, artifact, *, system_error=None, returncode=None):
        labels = {'python': 'Python', 'node': 'Node.js', 'npm': 'npm'}
        failures = {
            'start_failed': 'sürüm denetimi başlatılamadı',
            'timeout': 'sürüm denetimi 30 saniyelik sınırı aştı',
            'process_failed': 'sürüm denetimi hata ile kapandı',
            'version_mismatch': 'sürümü onaylı runtime kataloğuyla uyuşmuyor',
            'invalid_response': 'sürüm denetimi okunabilir bir yanıt vermedi',
        }
        self.reason = reason if reason in failures else 'invalid_response'
        self.artifact = artifact if artifact in labels else None
        self.code = 'runtime_validation_' + self.reason
        self.remedy = ('Seçili Node/Python kurulumunu ve çalışma iznini kontrol edin. '
                       'Manager sürümünü güncelleyin; hata kodu ve sayısal sistem kodunu inceleyin.')
        message = f"{labels.get(self.artifact, 'Runtime')} {failures[self.reason]}."
        for label, value in (('WinError', getattr(system_error, 'winerror', None)),
                             ('errno', getattr(system_error, 'errno', None)), ('Süreç çıkış kodu', returncode)):
            if type(value) is int:
                message += f' {label}: {value}.'
        super().__init__(message)


def _directory(home: Path, artifact: Artifact) -> Path:
    return home / "runtimes" / f"{artifact.name}-{artifact.version}"


def _inventory(directory: Path) -> dict[str, str]:
    from .startup_metrics import count_startup_work
    count_startup_work('runtime_inventory')
    result = {}
    receipt = directory / RECEIPT
    for path in sorted(directory.rglob("*")):
        _no_symlink(path)
        if path.is_file() and path != receipt:
            result[path.relative_to(directory).as_posix()] = _digest(path)
    return result


def _inventory_digest(files: dict[str, str]) -> str:
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _check_version(executable: Path, version: str, *, node: Path | None = None) -> None:
    name = 'npm' if node is not None else 'python' if executable.name == 'python.exe' else 'node'
    command = [str(executable), "--version"] if node is None else [str(node), str(executable), "--version"]
    if executable.name == "python.exe":
        command[1:1] = ["-I", "-S", "-B", "-X", "utf8", "-X", "frozen_modules=on"]
    try:
        completed = controlled_run(command, check=False, capture_output=True, text=True,
                                   encoding='utf-8', stdin=subprocess.DEVNULL, timeout=30,
                                   env={**os.environ, **MANAGED_RUNTIME_ENVIRONMENT})
    except subprocess.TimeoutExpired:
        raise RuntimeValidationError('timeout', name) from None
    except OSError as error:
        raise RuntimeValidationError('start_failed', name, system_error=error) from None
    except UnicodeError:
        raise RuntimeValidationError('invalid_response', name) from None
    if completed.returncode:
        raise RuntimeValidationError('process_failed', name, returncode=completed.returncode)
    rendered = completed.stdout.strip()
    expected = "Python " + version if executable.name == "python.exe" else version
    if rendered.removeprefix("v") != expected:
        raise RuntimeValidationError('version_mismatch', name)


def _npm_wrapper_files(node: Path, target: Path) -> dict[str, bytes]:
    if node.resolve().is_relative_to(target.parent.resolve()):
        relative_node = os.path.relpath(node, target / "bin").replace("/", "\\")
        executable = "%~dp0" + relative_node
    else:
        # System Node may live on a different drive or in a Unicode directory.
        # The process-local pointer avoids persisting it in a CMD code page.
        executable = "%AWCENTER_MANAGED_NODE%"
    return {
        f"bin/{command}.cmd": f'@echo off\r\nsetlocal DisableDelayedExpansion\r\n"{executable}" "%~dp0..\\package\\bin\\{command}-cli.js" %*\r\n'.encode("ascii")
        for command in ("npm", "npx")
    }


def _npm_wrappers(directory: Path, node: Path, target: Path) -> None:
    (directory / "bin").mkdir()
    for relative, content in _npm_wrapper_files(node, target).items():
        (directory / relative).write_bytes(content)


def _pinned_inventory(artifact: Artifact, current: dict[str, str], target: Path, node: Path | None) -> dict[str, str]:
    """Authenticate installed vendor bytes, then derive the selected launcher's wrappers."""
    files = current.copy()
    wrappers = _npm_wrapper_files(node, target) if artifact.name == "npm" else {}
    for relative in wrappers:
        files.pop(relative, None)
    if artifact.executable not in files or _inventory_digest(files) != INVENTORY_PINS[artifact.sha256]:
        raise LauncherError(f"managed {artifact.name} files differ from the reviewed archive")
    files.update({relative: hashlib.sha256(content).hexdigest() for relative, content in wrappers.items()})
    return files


def _trusted_inventory(home: Path, artifact: Artifact, catalog: dict[str, Artifact], current: dict[str, str],
                       *, node: Path | None = None) -> dict[str, str]:
    """Authenticate against a shipped tree pin or derive hashes from the pinned archive."""
    target = _directory(home, artifact)
    if artifact.name == "npm" and node is None:
        node = _directory(home, catalog["node"]) / catalog["node"].executable
    if artifact.sha256 in INVENTORY_PINS:
        return _pinned_inventory(artifact, current, target, node)
    archive = home / "cache/runtimes" / artifact.filename
    verify_artifact(archive, artifact)
    result = {}
    if artifact.archive == "zip":
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                relative = str(_safe_member(member.filename))
                if member.is_dir():
                    continue
                with source.open(member) as stream:
                    result[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    else:
        with tarfile.open(archive, "r:gz") as source:
            for member in source:
                relative = str(_safe_member(member.name))
                if member.isdir():
                    continue
                if not member.isfile():
                    raise LauncherError("reviewed runtime archive contains unsupported entries")
                with source.extractfile(member) as stream:
                    result[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    if artifact.name == "npm":
        for relative, content in _npm_wrapper_files(node, target).items():
            result[relative] = hashlib.sha256(content).hexdigest()
    return result


def _refresh_npm_wrappers(home: Path, target: Path, node: Path, current: dict, expected: dict) -> bool:
    """Permit runtime selection changes only for fully authenticated npm files."""
    artifact = load_catalog()['node']
    managed_node = _directory(home, artifact) / artifact.executable
    # The external placeholder only selects the environment-pointer wrapper;
    # its path is never written to a wrapper or executed.
    for previous_node in (managed_node, home / '.external-node'):
        reviewed = {**expected, **{relative: hashlib.sha256(content).hexdigest()
                                   for relative, content in _npm_wrapper_files(previous_node, target).items()}}
        if current != reviewed:
            continue
        for relative, content in _npm_wrapper_files(node, target).items():
            (target / relative).write_bytes(content)
        return True
    return False


def _stage_archive(artifact: Artifact, archive: Path | None, target: Path, node: Path | None,
                   *, publish: bool, progress) -> dict[str, str]:
    if archive is None:
        raise LauncherError(f"managed {artifact.name} disappeared during verification; retry provision")
    with tempfile.TemporaryDirectory(prefix=".tool-", dir=target.parent) as temporary:
        stage = Path(temporary) / "content"
        if callable(progress):
            progress(f'{artifact.name} runtime arşivi açılıyor')
        safe_extract(archive, stage, artifact.archive)
        if not (stage / artifact.executable).is_file():
            raise LauncherError("reviewed runtime executable is missing from its archive")
        if artifact.name == "npm":
            _npm_wrappers(stage, node, target)
        expected = _inventory(stage)
        if artifact.sha256 in INVENTORY_PINS and expected != _pinned_inventory(artifact, expected, target, node):
            raise LauncherError(f"staged {artifact.name} files differ from the reviewed archive")
        if publish:
            stage.rename(target)
        return expected


def _install(home: Path, artifact: Artifact, archive: Path | None, *, node: Path | None = None, progress=None) -> Path:
    target = _directory(home, artifact)
    _no_symlink(target)
    current = None
    if target.exists():
        if callable(progress):
            progress(f'{artifact.name} kurulu runtime dosyaları doğrulanıyor')
        current = _inventory(target)
    if current is not None and artifact.sha256 in INVENTORY_PINS:
        expected = _pinned_inventory(artifact, current, target, node)
    else:
        expected = _stage_archive(artifact, archive, target, node, publish=current is None, progress=progress)
    if current is not None and current != expected:
        if artifact.name != "npm" or not _refresh_npm_wrappers(home, target, node, current, expected):
            raise LauncherError(f"managed {artifact.name} files differ from the reviewed archive")
    if callable(progress):
        progress(f'{artifact.name} runtime sürümü doğrulanıyor')
    _check_version(target / artifact.executable, artifact.version, node=node)
    receipt = {"name": artifact.name, "version": artifact.version, "sha256": artifact.sha256, "files": expected}
    receipt_path = target / RECEIPT
    _no_symlink(receipt_path)
    contents = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    if not receipt_path.exists() or receipt_path.read_text(encoding="utf-8") != contents:
        if callable(progress):
            progress(f'{artifact.name} runtime doğrulama kaydı yazılıyor')
        # A crash must leave either the old receipt or a recoverable missing receipt.
        # Keep partial bytes outside the authenticated runtime tree on the same volume.
        with tempfile.TemporaryDirectory(prefix=".receipt-", dir=target.parent) as directory:
            staged = Path(directory) / RECEIPT
            with staged.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, receipt_path)
    return target / artifact.executable


def ensure_toolchain(home: Path, settings: SourceSettings, *, python_executable: Path | None = None,
                     node_executable: Path | None = None, progress=None, node_probe_deadline=None) -> dict[str, str]:
    """Install reviewed native artifacts; return environment overrides only.

    Hosts do not receive global PATH, registry or dependency-lock modifications.
    The caller owns when to apply the returned process-local environment.
    Explicit system Python/Node are validated and reused without their archives.
    A compatible npm beside system Node is reused; otherwise only npm is acquired.
    """
    home = Path(home)
    _no_symlink(home)
    if progress is None:
        progress = settings.progress
    catalog = load_catalog()
    if python_executable is not None:
        from .system_python import validate_python
        python_executable = validate_python(python_executable)
    npm_cli = None
    if node_executable is not None:
        from .system_node import find_npm_cli, validate_node
        from .probe_budget import deadline_at
        import time
        with deadline_at(node_probe_deadline if node_probe_deadline is not None else time.monotonic() + 60):
            node_executable = validate_node(node_executable)
            if callable(progress):
                progress('Kurulu npm sürümü denetleniyor')
            npm_cli = find_npm_cli(node_executable, catalog['npm'].version, compatible=True)
    for directory in (home, home / "cache", home / "cache" / "runtimes", home / "runtimes"):
        private_directory(directory, root=home)
    paths = {}
    for name in ("python", "node", "npm"):
        if name == "python" and python_executable is not None:
            paths[name] = python_executable
            continue
        if name == "node" and node_executable is not None:
            paths[name] = node_executable
            continue
        if name == "npm" and npm_cli is not None:
            paths[name] = npm_cli
            continue
        artifact = catalog[name]
        archive = None
        if artifact.sha256 not in INVENTORY_PINS or not _directory(home, artifact).exists():
            if callable(progress):
                progress(f'{name} runtime arşivi hazırlanıyor')
            archive = fetch_artifact(artifact, home / "cache/runtimes", settings)
        options = {'node': paths.get('node') if name == 'npm' else None}
        if progress is not None:
            options['progress'] = progress
        paths[name] = _install(home, artifact, archive, **options)
    return _environment(home, catalog, python_executable=python_executable,
                        node_executable=node_executable, npm_cli=paths['npm'])


def _environment(home: Path, catalog: dict[str, Artifact], *, python_executable: Path | None = None,
                 node_executable: Path | None = None, npm_cli: Path | None = None) -> dict[str, str]:
    paths = {name: _directory(home, artifact) / artifact.executable for name, artifact in catalog.items()}
    if python_executable is not None:
        paths['python'] = python_executable
    if node_executable is not None:
        from .system_node import find_npm_cli
        paths['node'] = node_executable
        if npm_cli is None:
            npm_cli = find_npm_cli(node_executable, catalog['npm'].version, compatible=True)
    if npm_cli is not None:
        paths['npm'] = npm_cli
    directories = [paths["python"].parent, paths["python"].parent / "Scripts", paths["node"].parent]
    managed_npm = _directory(home, catalog['npm'])
    if paths['npm'] == managed_npm / catalog['npm'].executable:
        directories.append(managed_npm / 'bin')
    else:
        directories.append(paths['npm'].parent)
    # npm must precede the npm bundled by Node, preserving the repository pin.
    directories.insert(0, directories.pop())
    return {**MANAGED_RUNTIME_ENVIRONMENT, "PATH": os.pathsep.join([*(str(path) for path in directories), os.environ.get("PATH", "")]), "AWCENTER_MANAGED_PYTHON": str(paths["python"]), "AWCENTER_MANAGED_NODE": str(paths["node"]), "AWCENTER_MANAGED_NPM_CLI": str(paths["npm"])}


def _has_receipt(target: Path, artifact: Artifact) -> bool:
    path = target / RECEIPT
    _no_symlink(path)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    if (receipt["name"], receipt["version"], receipt["sha256"]) != (artifact.name, artifact.version, artifact.sha256):
        raise ValueError("pin mismatch")
    return True


def inspect_toolchain(home: Path, *, python_executable: Path | None = None,
                      node_executable: Path | None = None, verify: bool = True) -> list[dict]:
    """Inspect full managed bytes by default, or only runtime identity/version."""
    checks = []
    catalog = load_catalog()
    verified_node = None
    for name, artifact in catalog.items():
        if name == 'python' and python_executable is not None:
            from .system_python import validate_python
            try:
                validate_python(python_executable)
                checks.append({'name': 'python', 'status': 'ready', 'detail': 'Sistem CPython 3.11 x64 doğrulandı; yönetilen arşiv gerekmez.'})
            except LauncherError as error:
                if isinstance(error, OperationCancelled):
                    raise
                checks.append({'name': 'python', 'status': 'invalid', 'detail': 'Kayıtlı sistem Python 3.11 x64 kullanılamıyor; otomatik kurulum yapılmadı.'})
            continue
        if name == 'node' and node_executable is not None:
            from .system_node import SystemNodeError, validate_node
            try:
                verified_node = validate_node(node_executable)
                checks.append({'name': 'node', 'status': 'ready', 'detail': 'Sistem Node x64 doğrulandı; yönetilen arşiv gerekmez.'})
            except SystemNodeError:
                checks.append({'name': 'node', 'status': 'invalid', 'detail': 'Kayıtlı sistem Node kullanılamıyor; otomatik kurulum yapılmadı.'})
            continue
        if name == 'npm' and node_executable is not None and verified_node is not None:
            from .system_node import find_npm_cli
            if find_npm_cli(verified_node, artifact.version, compatible=True) is not None:
                checks.append({'name': 'npm', 'status': 'ready', 'detail': 'Uyumlu sistem npm doğrulandı; yönetilen arşiv gerekmez.'})
                continue
        target = _directory(Path(home), artifact)
        check = {"name": name, "status": "missing", "detail": f"managed {name} {artifact.version} is missing"}
        if not target.exists():
            checks.append(check)
            continue
        try:
            _no_symlink(target)
            has_receipt = _has_receipt(target, artifact)
            if verify:
                inventory_options = {'node': Path(node_executable)} if name == 'npm' and node_executable is not None else {}
                current = _inventory(target)
                if current != _trusted_inventory(Path(home), artifact, catalog, current, **inventory_options):
                    raise ValueError("modified runtime")
            elif has_receipt:
                executable = target / _safe_member(artifact.executable)
                _no_symlink(executable)
                if not executable.is_file():
                    raise ValueError('runtime executable missing')
                if name == 'npm' and verified_node is None:
                    raise ValueError('validated Node executable missing')
                _check_version(executable, artifact.version,
                               **({'node': verified_node} if name == 'npm' else {}))
                if name == 'node':
                    verified_node = executable
            if has_receipt:
                detail = (f"managed {name} {artifact.version} verified" if verify else
                          f"{name} {artifact.version}: geliştirici hızlı kontrolü; tam dosya bütünlüğü doğrulanmadı.")
                check.update(status="ready", detail=detail)
            else:
                detail = (f"{name} dosyaları doğrulandı. Sürüm doğrulama kaydı eksik." if verify else
                          f"{name}: tamamlanmış runtime doğrulama kaydı eksik; hazırlama gerekli.")
                check.update(status="missing", detail=detail)
        except OperationCancelled:
            raise
        except (OSError, ValueError, KeyError, TypeError, LauncherError, tarfile.TarError, zipfile.BadZipFile):
            check.update(status="invalid", detail=f"managed {name} integrity check failed; provision requires reviewed files")
        checks.append(check)
    return checks


def toolchain_environment(home: Path, *, python_executable: Path | None = None,
                          node_executable: Path | None = None, verify: bool = True) -> dict[str, str]:
    """Return existing runtimes after the requested checks, without installation."""
    options = {}
    if python_executable is not None:
        # Older profiles can retain the Manager's windowed interpreter. Keep
        # the validated console base in the returned process environment too.
        if Path(python_executable).name.casefold() == 'pythonw.exe':
            from .system_python import validate_python
            python_executable = validate_python(python_executable)
        options['python_executable'] = python_executable
    if node_executable is not None:
        options['node_executable'] = node_executable
    inspection_options = {**options, **({'verify': False} if not verify else {})}
    if any(check["status"] != "ready" for check in inspect_toolchain(home, **inspection_options)):
        raise LauncherError("managed toolchain is incomplete or invalid; run provision")
    return _environment(Path(home), load_catalog(), **options)
