"""Trust boundaries for installer sources and archives."""
import hashlib
from contextlib import nullcontext
from http.client import IncompleteRead
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

    def test_verified_nested_local_runtime_prevents_network_in_every_mode(self):
        offline = self.root / "offline" / "runtimes"
        offline.mkdir(parents=True)
        (offline / self.artifact.filename).write_bytes(self.data)
        for mode in ('online', 'restricted', 'corporate', 'offline'):
            with self.subTest(mode=mode), patch.object(sources, "_download", side_effect=AssertionError('network used')):
                result = sources.fetch_artifact(self.artifact, self.root / mode, sources.SourceSettings(
                    repository="https://mirror.example/tools", offline_dir=offline.parent, mode=mode))
                self.assertEqual(result.read_bytes(), self.data)

    def test_corrupt_local_runtime_never_tries_network_in_every_mode(self):
        local = self.root / 'local'
        local.mkdir()
        (local / self.artifact.filename).write_bytes(b'changed')
        for mode in ('online', 'restricted', 'corporate', 'offline'):
            with self.subTest(mode=mode), patch.object(sources, '_download', side_effect=AssertionError('network used')):
                with self.assertRaisesRegex(LauncherError, 'SHA-256'):
                    sources.fetch_artifact(self.artifact, self.root / mode,
                                           sources.SourceSettings(offline_dir=local, mode=mode))

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

    def test_interrupted_transfer_retries_without_accepting_partial_bytes(self):
        attempts = []
        def download(url, destination, context):
            attempts.append(url)
            if len(attempts) == 1:
                destination.write_bytes(b'partial')
                raise IncompleteRead(b'partial', 20)
            destination.write_bytes(self.data)
        with patch.object(sources, '_download', side_effect=download):
            result = sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings())
        self.assertEqual(result.read_bytes(), self.data)
        self.assertEqual(attempts, [self.artifact.url, self.artifact.url])

    def test_short_content_length_response_is_retried_before_checksum_verification(self):
        response = unittest.mock.Mock()
        response.headers = {'Content-Length': str(len(self.data))}
        response.read.side_effect = [b'partial', b'', self.data, b'']
        opener = unittest.mock.Mock()
        opener.open.return_value = nullcontext(response)
        with patch.object(sources, 'build_opener', return_value=opener):
            result = sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings())
        self.assertEqual(result.read_bytes(), self.data)
        self.assertEqual(opener.open.call_count, 2)

    def test_complete_content_length_with_wrong_checksum_never_retries_or_falls_back(self):
        response = unittest.mock.Mock()
        response.headers = {'Content-Length': str(len(b'corrupt'))}
        response.read.side_effect = [b'corrupt', b'']
        opener = unittest.mock.Mock()
        opener.open.return_value = nullcontext(response)
        with patch.object(sources, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(LauncherError, 'SHA-256'):
                sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings(
                    repository='https://mirror.example/tools'))
        self.assertEqual(opener.open.call_count, 1)
        self.assertFalse((self.root / 'cache' / self.artifact.filename).exists())

    def test_exhausted_interrupted_transfers_try_the_next_permitted_source(self):
        attempts = []
        def download(url, destination, context):
            attempts.append(url)
            if url == self.artifact.url:
                destination.write_bytes(b'partial')
                raise IncompleteRead(b'partial', 20)
            destination.write_bytes(self.data)
        with patch.object(sources, '_download', side_effect=download):
            result = sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings(
                repository='https://mirror.example/tools'))
        self.assertEqual(result.read_bytes(), self.data)
        self.assertEqual(attempts, [self.artifact.url] * 3 + ['https://mirror.example/tools/example.zip'])

    def test_permission_failure_is_not_retried_or_hidden_by_source_fallback(self):
        with patch.object(sources, '_download', side_effect=PermissionError('private')) as download:
            with self.assertRaises(PermissionError):
                sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings(
                    repository='https://mirror.example/tools'))
        self.assertEqual(download.call_count, 1)

    def test_wrapped_permission_failure_does_not_retry_or_fallback(self):
        with patch.object(sources, '_download', side_effect=URLError(PermissionError('private'))) as download:
            with self.assertRaisesRegex(LauncherError, 'permission'):
                sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings(
                    repository='https://mirror.example/tools'))
        self.assertEqual(download.call_count, 1)

    def test_exhausted_corporate_rejections_never_request_public_sources(self):
        attempts = []
        def reject(url, *_):
            attempts.append(url)
            raise HTTPError(url, 407, 'private', {}, None)
        with patch.object(sources, '_download', side_effect=reject):
            with self.assertRaises(sources.ArtifactDownloadError) as caught:
                sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings(
                    repository='https://selected.example/tools', mode='corporate'))
        self.assertEqual(caught.exception.status, 407)
        self.assertEqual(attempts, ['https://selected.example/tools/example.zip',
                                    'https://selected.example/tools/runtimes/example.zip'])

    def test_exhausted_transient_http_rejections_preserve_the_final_status(self):
        with patch.object(sources, '_download', side_effect=HTTPError(self.artifact.url, 503, 'private', {}, None)) as download:
            with self.assertRaises(sources.ArtifactDownloadError) as caught:
                sources.fetch_artifact(self.artifact, self.root / 'cache', sources.SourceSettings())
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(download.call_count, 3)

    def test_safe_progress_precedes_each_permitted_source_attempt(self):
        events = []
        def download(url, destination, context):
            self.assertTrue(events)
            self.assertEqual(events[-1][0], 'progress')
            events.append(('download', url))
            if url == self.artifact.url:
                raise HTTPError(url, 403, 'private', {}, None)
            destination.write_bytes(self.data)
        settings = sources.SourceSettings(repository='https://mirror.example/tools',
            progress=lambda message: events.append(('progress', message)))
        with patch.object(sources, '_download', side_effect=download):
            result = sources.fetch_artifact(self.artifact, self.root / 'cache', settings)
        self.assertEqual(result.read_bytes(), self.data)
        progress = ' '.join(value for kind, value in events if kind == 'progress')
        self.assertNotIn('https://', progress)
        self.assertNotIn('private', progress)

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

    def test_online_http_rejection_advances_only_to_permitted_repository(self):
        urls = []
        def download(url, destination, context):
            urls.append(url)
            if url == self.artifact.url:
                raise HTTPError(url, 401, 'private', {}, None)
            destination.write_bytes(self.data)
        with patch.object(sources, '_download', side_effect=download):
            result = sources.fetch_artifact(self.artifact, self.root / 'cache',
                sources.SourceSettings(repository='https://mirror.example/tools'))
        self.assertEqual(result.read_bytes(), self.data)
        self.assertEqual(urls, [self.artifact.url, 'https://mirror.example/tools/example.zip'])

    def test_exhausted_http_rejections_preserve_safe_final_runtime_diagnostics(self):
        artifact = sources.Artifact("node", "1", "node.zip", self.artifact.url,
                                    self.artifact.sha256, "zip", "node.exe")
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
                            repository="https://mirror.example/tools"))
                self.assertEqual(download.call_count, 3)
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

    def test_http_not_found_closes_response_before_the_next_source(self):
        response = io.BytesIO(b"fixture-sensitive-detail")
        missing = HTTPError(self.artifact.url, 404, "missing", {}, response)
        def retrieve(url, destination, context):
            if url == self.artifact.url:
                raise missing
            self.assertTrue(response.closed)
            destination.write_bytes(self.data)
        with patch.object(sources, "_download", side_effect=retrieve) as download:
            result = sources.fetch_artifact(self.artifact, self.root / "cache",
                                            sources.SourceSettings(repository='https://mirror.example/tools'))
        self.assertEqual(result.read_bytes(), self.data)
        self.assertEqual(download.call_count, 2)
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
