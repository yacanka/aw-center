"""Trust boundaries for installer sources and archives."""
import hashlib
import io
import ssl
import tarfile
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts.launcher import installation_sources as sources
from scripts.launcher.model import LauncherError
from scripts.launcher.process import OperationCancelled, operation_control


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.data = b"reviewed artifact"
        self.artifact = sources.Artifact("example", "1", "example.zip", "https://public.example/example.zip", hashlib.sha256(self.data).hexdigest(), "zip", "example.exe")

    def test_public_unavailable_then_repository_then_nested_offline(self):
        offline = self.root / "offline" / "runtimes"
        offline.mkdir(parents=True)
        (offline / self.artifact.filename).write_bytes(self.data)
        settings = sources.SourceSettings(repository="https://mirror.example/tools", offline_dir=offline.parent)
        urls = []
        def unavailable(url, destination, context):
            urls.append(url)
            raise HTTPError(url, 404, "missing", {}, None)
        with patch.object(sources, "_download", side_effect=unavailable):
            result = sources.fetch_artifact(self.artifact, self.root / "cache", settings)
        self.assertEqual(result.read_bytes(), self.data)
        self.assertEqual(urls, [self.artifact.url, "https://mirror.example/tools/example.zip", "https://mirror.example/tools/runtimes/example.zip"])

    def test_hash_mismatch_does_not_fallback_or_cache(self):
        def corrupt(url, destination, context):
            destination.write_bytes(b"corrupt")
        with patch.object(sources, "_download", side_effect=corrupt):
            with self.assertRaises(LauncherError):
                sources.fetch_artifact(self.artifact, self.root / "cache", sources.SourceSettings())
        self.assertFalse((self.root / "cache" / self.artifact.filename).exists())

    def test_custom_ca_adds_to_default_root_trust(self):
        context = unittest.mock.Mock()
        with patch.object(sources.ssl, "create_default_context", return_value=context) as default, patch.object(sources, "_download", side_effect=URLError(TimeoutError())):
            with self.assertRaises(LauncherError):
                sources.fetch_artifact(self.artifact, self.root / "cache", sources.SourceSettings(ca_file=self.root / "corporate-ca.pem"))
        default.assert_called_once_with()
        context.load_verify_locations.assert_called_once_with(cafile=str(self.root / "corporate-ca.pem"))

    def test_tls_failure_does_not_fallback(self):
        with patch.object(sources, "_download", side_effect=URLError(ssl.SSLCertVerificationError("private detail"))) as download:
            with self.assertRaisesRegex(LauncherError, "TLS"):
                sources.fetch_artifact(self.artifact, self.root / "cache", sources.SourceSettings(repository="https://mirror.example"))
        self.assertEqual(download.call_count, 1)

    def test_availability_retry_is_bounded(self):
        with patch.object(sources, "_download", side_effect=URLError(TimeoutError())) as download:
            with self.assertRaises(LauncherError):
                sources.fetch_artifact(self.artifact, self.root / "cache", sources.SourceSettings())
        self.assertEqual(download.call_count, 3)

    def test_cancelled_retrieval_never_starts_an_acquisition_attempt(self):
        stop = threading.Event()
        stop.set()
        attempts = []
        def download(*_):
            attempts.append('started')
        with operation_control(stop), patch.object(sources, '_download', side_effect=download):
            with self.assertRaises(OperationCancelled):
                sources._retrieve(self.artifact.url, self.root / 'download', None)
        self.assertEqual(attempts, [])

    def test_cancellation_between_retries_prevents_the_next_network_attempt(self):
        stop = threading.Event()
        attempts = []
        def unavailable(*_):
            attempts.append('started')
            stop.set()
            raise URLError(TimeoutError())
        with operation_control(stop), patch.object(sources, '_download', side_effect=unavailable):
            with self.assertRaises(OperationCancelled):
                sources._retrieve(self.artifact.url, self.root / 'download', None)
        self.assertEqual(attempts, ['started'])

    def test_download_cancellation_stops_at_the_next_chunk_boundary(self):
        stop = threading.Event()
        reads = []
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def read(self, _):
                reads.append('read')
                if len(reads) == 1:
                    stop.set()
                    return b'first'
                return b'second' if len(reads) == 2 else b''
        opener = unittest.mock.Mock()
        opener.open.return_value = Response()
        destination = self.root / 'download'
        with operation_control(stop), patch.object(sources, 'build_opener', return_value=opener):
            with self.assertRaises(OperationCancelled):
                sources._download(self.artifact.url, destination, None)
        self.assertEqual(reads, ['read'])
        self.assertEqual(destination.read_bytes(), b'first')

    def test_unsafe_urls_and_filename_rejected_before_writes(self):
        for url in ("http://example.com/file", "https://user:secret@example.com/file"):
            artifact = sources.Artifact("a", "1", "a.zip", url, "a" * 64, "zip", "a.exe")
            with self.subTest(url=url), self.assertRaises(LauncherError):
                sources.fetch_artifact(artifact, self.root / "cache", sources.SourceSettings())
        self.assertFalse((self.root / "cache").exists())

    def test_signed_https_redirect_is_allowed_but_credentials_and_downgrade_are_not(self):
        from urllib.request import Request
        request = Request("https://public.example/file")
        redirect = sources._SecureRedirect()
        result = redirect.redirect_request(request, None, 302, "found", {}, "https://cdn.example/file?signature=opaque")
        self.assertEqual(result.full_url, "https://cdn.example/file?signature=opaque")
        for target in ("http://cdn.example/file", "https://user:password@cdn.example/file"):
            with self.subTest(target=target), self.assertRaises(LauncherError):
                redirect.redirect_request(request, None, 302, "found", {}, target)

    def test_authorization_failure_does_not_fallback(self):
        with patch.object(sources, "_download", side_effect=HTTPError(self.artifact.url, 401, "private", {}, None)) as download:
            with self.assertRaises(LauncherError):
                sources.fetch_artifact(self.artifact, self.root / "cache", sources.SourceSettings(repository="https://mirror.example"))
        self.assertEqual(download.call_count, 1)

    def test_http_rejection_preserves_safe_runtime_diagnostics_without_fallback(self):
        artifact = sources.Artifact("node", "1", "node.zip", self.artifact.url,
                                    self.artifact.sha256, "zip", "node.exe")
        offline = self.root / "offline"
        offline.mkdir()
        (offline / artifact.filename).write_bytes(self.data)
        marker = "fixture-sensitive-detail"
        for status in (401, 403, 407):
            with self.subTest(status=status):
                response = io.BytesIO(marker.encode())
                rejected = HTTPError(f"https://upstream.example/private?token={marker}",
                                     status, marker, {"X-Private": marker}, response)
                cache = self.root / f"cache-{status}"
                with patch.object(sources, "_download", side_effect=rejected) as download:
                    with self.assertRaises(LauncherError) as raised:
                        sources.fetch_artifact(artifact, cache, sources.SourceSettings(
                            repository="https://mirror.example/tools", offline_dir=offline))
                self.assertEqual(download.call_count, 1)
                self.assertFalse((cache / artifact.filename).exists())
                error = raised.exception
                self.assertEqual(getattr(error, "code", None), "artifact_http_rejected")
                self.assertIsInstance(error, sources.ArtifactDownloadError)
                self.assertEqual(error.status, status)
                self.assertEqual(error.artifact, "node")
                self.assertIn(f"HTTP {status}", str(error))
                self.assertIn("Node.js", str(error))
                self.assertIsInstance(error.remedy, str)
                self.assertTrue(error.remedy)
                rendered = str(error) + error.remedy
                self.assertNotIn(marker, rendered)
                self.assertNotIn("upstream.example", rendered)
                self.assertNotIn("https://", rendered)
                self.assertTrue(response.closed)

    def test_http_not_found_closes_response_before_local_artifact_fallback(self):
        offline = self.root / "offline"
        offline.mkdir()
        (offline / self.artifact.filename).write_bytes(self.data)
        response = io.BytesIO(b"fixture-sensitive-detail")
        missing = HTTPError(self.artifact.url, 404, "missing", {}, response)
        with patch.object(sources, "_download", side_effect=missing) as download:
            result = sources.fetch_artifact(self.artifact, self.root / "cache",
                                            sources.SourceSettings(offline_dir=offline))
        self.assertEqual(result.read_bytes(), self.data)
        self.assertEqual(download.call_count, 1)
        self.assertTrue(response.closed)

    def test_retryable_http_responses_are_closed_before_the_next_attempt(self):
        responses = []
        failures = []
        closed_before_attempt = []

        def unavailable(url, destination, context):
            closed_before_attempt.append(all(response.closed for response in responses))
            response = io.BytesIO(b"fixture-sensitive-detail")
            responses.append(response)
            failures.append(HTTPError(url, 503, "unavailable", {}, response))
            raise failures[-1]

        with patch.object(sources, "_download", side_effect=unavailable) as download:
            with self.assertRaises(LauncherError):
                sources.fetch_artifact(self.artifact, self.root / "cache", sources.SourceSettings())
        self.assertEqual(download.call_count, 3)
        self.assertEqual(len(responses), 3)
        self.assertEqual(closed_before_attempt, [True, True, True])
        self.assertTrue(all(response.closed for response in responses))

    def test_verified_cache_avoids_network_and_corruption_fails_closed(self):
        cache = self.root / "cache"
        cache.mkdir()
        cached = cache / self.artifact.filename
        cached.write_bytes(self.data)
        with patch.object(sources, "_download") as download:
            self.assertEqual(sources.fetch_artifact(self.artifact, cache, sources.SourceSettings()), cached)
            cached.write_bytes(b"tampered")
            with self.assertRaises(LauncherError):
                sources.fetch_artifact(self.artifact, cache, sources.SourceSettings())
        download.assert_not_called()

    def test_zip_devices_rejected(self):
        archive = self.root / "device.zip"
        with zipfile.ZipFile(archive, "w") as output:
            info = zipfile.ZipInfo("device")
            info.external_attr = 0o020666 << 16
            output.writestr(info, b"")
        with self.assertRaises(LauncherError):
            sources.safe_extract(archive, self.root / "extract", "zip")

    def test_zip_traversal_and_symlink_rejected_before_extraction(self):
        for name, mode in (("../outside", 0o100644), ("C:/outside", 0o100644), ("link", 0o120777), ("a\\..\\outside", 0o100644)):
            archive = self.root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as output:
                info = zipfile.ZipInfo(name)
                info.external_attr = mode << 16
                output.writestr(info, "target")
            destination = self.root / "extract"
            with self.subTest(name=name), self.assertRaises(LauncherError):
                sources.safe_extract(archive, destination, "zip")
            self.assertFalse(destination.exists())

    def test_tar_links_rejected(self):
        archive = self.root / "bad.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            info = tarfile.TarInfo("link")
            info.type = tarfile.SYMTYPE
            info.linkname = "outside"
            output.addfile(info)
        with self.assertRaises(LauncherError):
            sources.safe_extract(archive, self.root / "extract", "tar.gz")

    def test_valid_zip_extracts(self):
        archive = self.root / "good.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("folder/file.txt", self.data)
        sources.safe_extract(archive, self.root / "extract", "zip")
        self.assertEqual((self.root / "extract/folder/file.txt").read_bytes(), self.data)

    def test_catalog_uses_reviewed_pins(self):
        catalog = sources.load_catalog()
        self.assertEqual(set(catalog), {"python", "node", "npm"})
        self.assertEqual(catalog["python"].sha256, "75cb501dc11c7b55c6b447c58e4910bce5b1f609f1017328b4f3a858dfaf5428")
        self.assertEqual(catalog["node"].version, "22.23.4")
        self.assertEqual(catalog["npm"].version, "10.9.4")


if __name__ == "__main__":
    unittest.main()
