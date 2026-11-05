"""Reviewed installer artifacts, TLS-only retrieval and safe archive handling.

Repository mirrors supply bytes only: their manifests can never authorize code.
SHA-256 trust comes exclusively from the catalog shipped with this source tree.
Proxy configuration is inherited from the process; credentials are never printed.
"""
from __future__ import annotations

import hashlib
from http.client import IncompleteRead
import json
import os
import re
import shutil
import socket
import ssl
import stat
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener

from .model import LauncherError
from .process import check_cancelled

MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * MAX_ARTIFACT_BYTES
CATALOG_PATH = Path(__file__).with_name("installation_catalog.json")


class ArtifactDownloadError(LauncherError):
    """A rejected download with only reviewed labels and numeric HTTP status."""

    def __init__(self, status, *, artifact=None):
        labels = {"python": "Python", "node": "Node.js", "npm": "npm"}
        self.status = status if type(status) is int and 100 <= status <= 599 else None
        self.artifact = artifact if artifact in labels else None
        self.code = "artifact_http_rejected"
        self.remedy = {
            401: "Runtime deposu kimlik doğrulaması istiyor. Kurumun onaylı depo erişimini kullanın; URL'ye kullanıcı bilgisi eklemeyin.",
            403: "Runtime arşivine erişim reddedildi. Kurumsal ağ/proxy izinlerini ve seçili runtime deposunun erişimini kontrol edin.",
            407: "Proxy kimlik doğrulaması gerekli. Kurumsal proxy oturumunu ve erişim ayarlarını kontrol edin.",
        }.get(self.status, "Runtime deposunun HTTP erişim politikasını ve ağ bağlantısını kontrol edin.")
        message = f"{labels.get(self.artifact, 'Runtime')} arşivi indirme isteği kaynak sunucusu tarafından reddedildi."
        if self.status is not None:
            message += f" HTTP {self.status}."
        super().__init__(message)


@dataclass(frozen=True)
class Artifact:
    name: str
    version: str
    filename: str
    url: str
    sha256: str
    archive: str
    executable: str


@dataclass(frozen=True)
class SourceSettings:
    repository: str | Path | None = None
    offline_dir: Path | None = None
    python_index_url: str | None = None
    npm_registry_url: str | None = None
    ca_file: Path | None = None
    mode: str = "online"
    runtime_dirs: tuple[Path, ...] = ()
    progress: Callable[[str], None] | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.mode not in {"online", "restricted", "corporate", "offline"}:
            raise LauncherError("Kaynak modu online, restricted, corporate veya offline olmalıdır.")

    def report(self, message: str) -> None:
        if self.progress:
            self.progress(message)


def acquisition_urls(settings: SourceSettings, public: str, selected: str | None) -> list[str]:
    """Return only network sources explicitly permitted by the selected mode."""
    if settings.mode == "offline":
        return []
    urls = [public] if settings.mode == "online" else []
    if selected:
        urls.append(_https_url(selected))
    if settings.mode == "restricted" and public not in urls:
        urls.append(public)
    return urls


def _https_url(url: str, *, allow_query: bool = False) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise LauncherError("artifact sources require HTTPS without URL credentials")
    if (parsed.query and not allow_query) or parsed.fragment or any(character in url for character in "\r\n"):
        raise LauncherError("artifact source URLs cannot contain queries or fragments")
    return url


def _validate_artifact(artifact: Artifact) -> None:
    _https_url(artifact.url)
    _safe_member(artifact.filename)
    if "/" in artifact.filename or "\\" in artifact.filename:
        raise LauncherError("artifact filename must be a single safe filename")
    if not re.fullmatch(r"[0-9a-f]{64}", artifact.sha256):
        raise LauncherError("artifact SHA-256 pin is missing or invalid")
    if artifact.archive not in {"zip", "tar.gz"}:
        raise LauncherError("unsupported artifact archive")
    _safe_member(artifact.executable)


def load_catalog() -> dict[str, Artifact]:
    """Read only the reviewed catalog adjacent to the launcher source."""
    try:
        values = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        catalog = {name: Artifact(**value) for name, value in values.items()}
        for name, artifact in catalog.items():
            if artifact.name != name:
                raise ValueError("catalog identity mismatch")
            _validate_artifact(artifact)
        return catalog
    except (OSError, ValueError, TypeError) as error:
        raise LauncherError("reviewed installation catalog is invalid") from error


def _no_symlink(path: Path) -> None:
    current = path.absolute()
    for candidate in (current, *current.parents):
        try:
            information = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(information.st_mode) or getattr(information, "st_file_attributes", 0) & 0x400:
            raise LauncherError("symbolic links and reparse points are not allowed in installation paths")


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _verify(path: Path, artifact: Artifact) -> None:
    _no_symlink(path)
    if not path.is_file() or path.stat().st_size > MAX_ARTIFACT_BYTES or _digest(path) != artifact.sha256:
        raise LauncherError(f"SHA-256 verification failed for {artifact.name}")


class _SecureRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        _https_url(newurl, allow_query=True)
        return super().redirect_request(request, response, code, message, headers, newurl)


def _download(url: str, destination: Path, context: ssl.SSLContext) -> None:
    opener = build_opener(_SecureRedirect(), HTTPSHandler(context=context))
    with opener.open(url, timeout=30) as response, destination.open("wb") as output:
        declared = getattr(response, 'headers', {}).get('Content-Length')
        expected = None
        if isinstance(declared, str) and re.fullmatch(r'[0-9]+', declared.strip()):
            declared = declared.strip().lstrip('0') or '0'
            if len(declared) > len(str(MAX_ARTIFACT_BYTES)) or int(declared) > MAX_ARTIFACT_BYTES:
                raise LauncherError("artifact exceeds the download size limit")
            expected = int(declared)
        size = 0
        while True:
            check_cancelled()
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARTIFACT_BYTES:
                raise LauncherError("artifact exceeds the download size limit")
            output.write(chunk)
        if expected is not None and size < expected:
            raise IncompleteRead(b'', expected - size)


def _retrieve(url: str, destination: Path, context: ssl.SSLContext) -> bool:
    """Retry transient availability failures, never integrity/TLS failures."""
    status = None
    for attempt in range(3):
        check_cancelled()
        status = None
        try:
            _download(url, destination, context)
            return True
        except HTTPError as error:
            try:
                if error.code == 404:
                    return False
                if error.code not in {408, 429, 500, 502, 503, 504}:
                    raise ArtifactDownloadError(error.code) from None
                status = error.code
            finally:
                error.close()
        except (ssl.SSLError, ssl.CertificateError):
            raise LauncherError("artifact TLS verification failed") from None
        except URLError as error:
            if isinstance(error.reason, (ssl.SSLError, ssl.CertificateError)):
                raise LauncherError("artifact TLS verification failed") from None
            if isinstance(error.reason, PermissionError):
                raise LauncherError("artifact download blocked by permissions") from None
            if not isinstance(error.reason, (OSError, TimeoutError, socket.timeout)):
                raise LauncherError("artifact download failed") from None
        except (TimeoutError, ConnectionError, IncompleteRead):
            pass
    if status is not None:
        raise ArtifactDownloadError(status)
    return False


def fetch_artifact(artifact: Artifact, cache: Path, settings: SourceSettings) -> Path:
    """Fetch verified bytes using only sources permitted by the selected mode.

    Integrity or TLS errors fail closed. A corrupt existing cache is also fatal,
    so retries cannot accidentally mask a tampered trusted artifact.
    """
    _validate_artifact(artifact)
    repository = settings.repository
    remote_repository = isinstance(repository, str) and repository.lower().startswith(("http:", "https:"))
    if remote_repository:
        _https_url(repository)
    cache = Path(cache)
    _no_symlink(cache)
    destination = cache / artifact.filename
    if destination.exists():
        _verify(destination, artifact)
        return destination
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=cache) as temporary:
        stage = Path(temporary) / artifact.filename
        directories = list(settings.runtime_dirs)
        if repository and not remote_repository:
            directories.append(Path(repository))
        if settings.offline_dir:
            directories.append(Path(settings.offline_dir))
        if _copy_local_artifact(artifact, directories, stage, destination):
            settings.report(f'{artifact.name}: doğrulanmış yerel arşiv kullanılıyor')
            return destination
        context = ssl.create_default_context() if settings.mode != "offline" else None
        if settings.ca_file and context is not None:
            try:
                context.load_verify_locations(cafile=str(settings.ca_file))
            except (OSError, ssl.SSLError):
                raise LauncherError("configured artifact CA bundle could not be loaded") from None
        selected = str(repository).rstrip("/") + "/" + artifact.filename if remote_repository else None
        urls = acquisition_urls(settings, artifact.url, selected)
        if remote_repository and settings.mode != "offline":
            nested = str(repository).rstrip("/") + "/runtimes/" + artifact.filename
            urls.insert(1, nested) if settings.mode == 'restricted' else urls.append(nested)
        rejection = None
        for index, url in enumerate(urls):
            attempt = Path(temporary) / str(index)
            attempt.mkdir()
            stage = attempt / artifact.filename
            settings.report(f'{artifact.name}: izinli kaynak {index + 1}/{len(urls)} deneniyor')
            try:
                retrieved = _retrieve(url, stage, context)
            except ArtifactDownloadError as error:
                rejection = ArtifactDownloadError(error.status, artifact=artifact.name)
                settings.report(f'{artifact.name}: HTTP {error.status}; sıradaki izinli kaynak deneniyor')
                continue
            if retrieved:
                _verify(stage, artifact)
                os.replace(stage, destination)
                return destination
            settings.report(f'{artifact.name}: kaynak erişilemiyor; sıradaki izinli kaynak deneniyor')
        if rejection is not None:
            raise rejection from None
    raise LauncherError(f"verified {artifact.name} artifact unavailable from configured sources")


def _copy_local_artifact(artifact, directories, stage, destination) -> bool:
    for directory in dict.fromkeys(map(Path, directories)):
        for source in (directory / artifact.filename, directory / 'runtimes' / artifact.filename):
            check_cancelled()
            if source.exists():
                _verify(source, artifact)
                shutil.copyfile(source, stage)
                _verify(stage, artifact)
                os.replace(stage, destination)
                return True
    return False


def _safe_member(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    parts = normalized.rstrip("/").split("/")
    if path.is_absolute() or not parts or any(part in {"", ".", ".."} or ":" in part or part.endswith((" ", ".")) for part in parts):
        raise LauncherError("unsafe archive entry")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if any(part.split(".")[0].upper() in reserved for part in parts):
        raise LauncherError("unsafe Windows archive entry")
    return path


def safe_extract(archive: Path, destination: Path, kind: str) -> None:
    """Validate all members before writing; reject links, devices and traversal."""
    _no_symlink(destination)
    if destination.exists():
        raise LauncherError("archive destination already exists")
    if kind == "zip":
        with zipfile.ZipFile(archive) as source:
            entries = [(info, _safe_member(info.filename)) for info in source.infolist()]
            if sum(info.file_size for info, _ in entries) > MAX_EXPANDED_BYTES:
                raise LauncherError("archive exceeds the expanded size limit")
            allowed_types = {0, stat.S_IFREG, stat.S_IFDIR}
            if any(stat.S_IFMT(info.external_attr >> 16) not in allowed_types for info, _ in entries):
                raise LauncherError("archive links and special files are not allowed")
            _unique_members([str(path).casefold() for _, path in entries])
            destination.mkdir(parents=True)
            for info, path in entries:
                target = destination.joinpath(*path.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(info) as input_file, target.open("xb") as output:
                    shutil.copyfileobj(input_file, output)
        return
    if kind != "tar.gz":
        raise LauncherError("unsupported artifact archive")
    with tarfile.open(archive, "r:gz") as source:
        entries = [(info, _safe_member(info.name)) for info in source.getmembers()]
        if sum(info.size for info, _ in entries) > MAX_EXPANDED_BYTES:
            raise LauncherError("archive exceeds the expanded size limit")
        if any(not (info.isfile() or info.isdir()) for info, _ in entries):
            raise LauncherError("archive links and special files are not allowed")
        _unique_members([str(path).casefold() for _, path in entries])
        destination.mkdir(parents=True)
        for info, path in entries:
            target = destination.joinpath(*path.parts)
            if info.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(info) as input_file, target.open("xb") as output:
                shutil.copyfileobj(input_file, output)


def _unique_members(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise LauncherError("duplicate archive entries are not allowed")
