"""Verify the immutable Vite artifact served by Django."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.test import Client

MAX_INDEX_BYTES = 2 * 1024 * 1024


class FrontendArtifactError(RuntimeError):
    """Represent a deployment-blocking frontend artifact defect."""


class _AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attributes):
        """Collect script and stylesheet references from the SPA shell."""

        attribute_name = "src" if tag == "script" else "href" if tag == "link" else ""
        values = dict(attributes)
        if attribute_name and values.get(attribute_name):
            self.references.append(values[attribute_name])


def verify_frontend_artifact():
    """Verify the Vite shell, referenced assets, and Django SPA fallback."""

    index_bytes = read_index_bytes()
    asset_paths = extract_asset_paths(decode_index(index_bytes))
    verify_asset_types(asset_paths)
    for asset_path in asset_paths:
        verify_asset_file(asset_path)
    verify_spa_response(index_bytes)
    verify_static_responses(asset_paths)
    return {"index_bytes": len(index_bytes), "asset_count": len(asset_paths)}


def read_index_bytes():
    """Read one bounded UTF-8 SPA shell from the configured dist directory."""

    index_path = Path(settings.FRONTEND_DIST_DIR) / "index.html"
    if not index_path.is_file():
        raise FrontendArtifactError(f"Frontend entry file is missing: {index_path}")
    if index_path.stat().st_size > MAX_INDEX_BYTES:
        raise FrontendArtifactError("Frontend entry file exceeds the safety limit.")
    try:
        return index_path.read_bytes()
    except OSError as error:
        raise FrontendArtifactError("Frontend entry file cannot be read.") from error


def decode_index(index_bytes):
    """Decode the generated shell through a deployment-safe error boundary."""

    try:
        return index_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FrontendArtifactError("Frontend entry file is not valid UTF-8.") from error


def extract_asset_paths(index_html):
    """Return unique same-origin Vite asset paths from an HTML document."""

    parser = _AssetParser()
    parser.feed(index_html)
    prefix = f"{settings.STATIC_URL.rstrip('/')}/assets/"
    paths = [urlsplit(reference).path for reference in parser.references]
    return list(dict.fromkeys(path for path in paths if path.startswith(prefix)))


def verify_asset_types(asset_paths):
    """Require executable and stylesheet entry assets in the Vite shell."""

    suffixes = {Path(asset_path).suffix.lower() for asset_path in asset_paths}
    if ".js" not in suffixes or ".css" not in suffixes:
        raise FrontendArtifactError("Frontend shell must reference JavaScript and CSS assets.")


def verify_asset_file(asset_path):
    """Require non-empty source and collected copies of a referenced asset."""

    prefix = f"{settings.STATIC_URL.rstrip('/')}/assets/"
    relative_path = asset_path.removeprefix(prefix)
    asset_root = Path(settings.FRONTEND_ASSETS_DIR).resolve()
    source = (asset_root / relative_path).resolve()
    if not source.is_relative_to(asset_root):
        raise FrontendArtifactError("Frontend shell contains an unsafe asset path.")
    if not source.is_file() or source.stat().st_size == 0:
        raise FrontendArtifactError(f"Referenced frontend asset is missing or empty: {asset_path}")
    verify_collected_asset(relative_path)


def verify_collected_asset(relative_path):
    """Require collectstatic output for one immutable frontend asset."""

    static_root = Path(settings.STATIC_ROOT).resolve()
    collected = (static_root / "assets" / relative_path).resolve()
    if not collected.is_relative_to(static_root):
        raise FrontendArtifactError("Collected frontend asset path is unsafe.")
    if not collected.is_file() or collected.stat().st_size == 0:
        raise FrontendArtifactError(
            f"Collected frontend asset is missing or empty: assets/{relative_path}"
        )


def verify_spa_response(expected_body):
    """Verify Django returns the exact shell for a nested application route."""

    client = Client(HTTP_HOST=verification_host())
    response = client.get("/app/jobs", secure=True)
    body = response_body(response)
    if response.status_code != 200 or body != expected_body:
        raise FrontendArtifactError("Django did not serve the configured SPA artifact.")


def verify_static_responses(asset_paths):
    """Verify WhiteNoise serves one non-empty JavaScript and CSS entry asset."""

    client = Client(HTTP_HOST=verification_host())
    for suffix in (".js", ".css"):
        asset_path = next(path for path in asset_paths if path.endswith(suffix))
        response = client.get(asset_path, secure=True)
        if response.status_code != 200 or not response_body(response):
            raise FrontendArtifactError(f"Django did not serve frontend asset: {asset_path}")


def response_body(response):
    """Read a deployment-test response body regardless of streaming mode."""

    return b"".join(response.streaming_content) if response.streaming else response.content


def verification_host():
    """Return one concrete configured host suitable for Django's test client."""

    hosts = [
        host
        for host in settings.ALLOWED_HOSTS
        if host and host != "*" and not host.startswith(".")
    ]
    return hosts[0] if hosts else "localhost"
