"""Security and fencing tests for static automation metadata and Windows bridge APIs."""

import ast
import hashlib
import tempfile
from datetime import datetime, timedelta, timezone as datetime_timezone
from pathlib import Path
from urllib.parse import quote

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework.test import APIClient

from awcenter.job_executors import local_job_kinds, resolve_job_executor
from jobs.contracts import JobExecutionFailure
from jobs.models import Job, JobStatus
from jobs.services import create_job
from jobs.worker import claim_next_job

from .catalog import (
    EXECUTOR_CATALOG,
    LOCAL_QUEUE,
    WINDOWS_QUEUE,
    executor_kinds,
)


def test_certificate_identity():
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AW Center"),
            x509.NameAttribute(NameOID.COMMON_NAME, "awcenter-windows-agent-01"),
        ]
    )
    now = datetime.now(datetime_timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem = certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return (
        quote(pem, safe=""),
        certificate.fingerprint(hashes.SHA256()).hex().upper(),
        certificate.subject.rfc4514_string(),
    )


CERTIFICATE_HEADER, FINGERPRINT, SUBJECT = test_certificate_identity()


@override_settings(
    DOORS_ENABLED=True,
    WINDOWS_BRIDGE_ENABLED=True,
    WINDOWS_BRIDGE_TRUST_PROXY_HEADERS=True,
    WINDOWS_BRIDGE_TRUSTED_PROXY_IPS=["127.0.0.1"],
    WINDOWS_BRIDGE_CLIENT_FINGERPRINTS=[FINGERPRINT],
    WINDOWS_BRIDGE_CLIENT_SUBJECTS=[SUBJECT],
    JOB_LEASE_SECONDS=60,
    JOB_WORKER_STALE_SECONDS=10,
    JOB_MAX_OUTPUT_BYTES=1024 * 1024,
)
class WindowsBridgeApiTests(TestCase):
    """Exercise the complete outbound-only bridge data-plane contract."""

    def setUp(self):
        self.private_root = Path(tempfile.mkdtemp())
        self.storage_override = override_settings(PRIVATE_MEDIA_ROOT=self.private_root)
        self.storage_override.enable()
        self.user = get_user_model().objects.create_user("automation-owner")
        self.client = APIClient()
        cache.clear()

    def tearDown(self):
        cache.clear()
        self.storage_override.disable()
        import shutil

        shutil.rmtree(self.private_root, ignore_errors=True)

    def test_claim_uses_only_windows_allowlist_and_returns_no_infrastructure_credentials(self):
        """An older local job cannot cross the Windows queue trust boundary."""

        local, _ = create_job(
            self.user, "media.convert", "Local", {}, self.json_upload("local.json")
        )
        remote = self.create_windows_job()

        response = self.claim()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["job"]["id"], str(remote.id))
        self.assertEqual(response.data["job"]["kind"], "doors.run_dxl")
        self.assertGreater(response.data["job"]["heartbeat_interval_seconds"], 0)
        self.assertGreater(response.data["job"]["lease_seconds"], 0)
        self.assertTrue(response.data["job"]["lease_expires_at"].endswith("+00:00"))
        self.assertEqual(response.data["queue"], WINDOWS_QUEUE)
        self.assertEqual(response.data["contract"]["database_access"], "none")
        self.assertEqual(response.data["contract"]["cache_access"], "none")
        serialized = response.content.decode("utf-8").casefold()
        self.assertNotIn("database_url", serialized)
        self.assertNotIn("cache_url", serialized)
        self.assertNotIn("postgres://", serialized)
        self.assertNotIn("redis://", serialized)
        local.refresh_from_db()
        self.assertEqual(local.status, JobStatus.QUEUED)

    def test_agent_status_selects_idle_poll_cadence(self):
        response = self.client.get(
            "/internal/bridge/v1/status/",
            secure=True,
            **self.mtls_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data["poll_interval_seconds"], 0)

    def test_bridge_errors_are_never_cacheable(self):
        response = self.client.post(
            "/internal/bridge/v1/claims/?credential=forbidden",
            {},
            format="json",
            secure=True,
            **self.mtls_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Pragma"], "no-cache")

    def test_input_download_is_sha_verified_and_single_use(self):
        """A transfer capability cannot replay the private input artifact."""

        self.create_windows_job()
        claim = self.claim().data["job"]
        headers = self.execution_headers(
            claim["execution_token"], claim["input"]["artifact_token"]
        )

        first = self.client.get(
            claim["input"]["download_url"], secure=True, **self.mtls_headers(), **headers
        )
        content = b"".join(first.streaming_content)
        replay = self.client.get(
            claim["input"]["download_url"], secure=True, **self.mtls_headers(), **headers
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(hashlib.sha256(content).hexdigest(), first["X-AWC-Artifact-SHA256"])
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(replay.data["code"], "BRIDGE_TRANSFER_REJECTED")

    def test_heartbeat_advances_progress_and_reports_cancellation(self):
        """Remote progress uses the same fenced state transition as local executors."""

        job = self.create_windows_job()
        claim = self.claim().data["job"]
        headers = self.execution_headers(claim["execution_token"])

        progress = self.client.post(
            claim["heartbeat_url"],
            {"progress": 35},
            format="json",
            secure=True,
            **self.mtls_headers(),
            **headers,
        )
        Job.objects.filter(pk=job.pk).update(status=JobStatus.CANCEL_REQUESTED)
        cancelled = self.client.post(
            claim["heartbeat_url"],
            {},
            format="json",
            secure=True,
            **self.mtls_headers(),
            **headers,
        )

        job.refresh_from_db()
        self.assertEqual(progress.status_code, 200)
        self.assertGreaterEqual(job.progress, 35)
        self.assertEqual(cancelled.status_code, 200)
        self.assertTrue(cancelled.data["cancel_requested"])

    def test_output_requires_matching_sha_and_completes_once(self):
        """A bad digest cannot consume or publish the output capability."""

        job = self.create_windows_job()
        claim = self.claim().data["job"]
        content = b'{"accessible":true}'
        headers = self.execution_headers(
            claim["execution_token"], claim["output"]["artifact_token"]
        )
        bad = self.complete(
            claim,
            headers,
            content,
            "0" * 64,
        )
        succeeded = self.complete(
            claim,
            headers,
            content,
            hashlib.sha256(content).hexdigest(),
        )
        replay = self.complete(
            claim,
            headers,
            content,
            hashlib.sha256(content).hexdigest(),
        )

        job.refresh_from_db()
        self.assertEqual(bad.status_code, 409)
        self.assertEqual(succeeded.status_code, 200)
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(job.output_sha256, hashlib.sha256(content).hexdigest())
        self.assertEqual(replay.status_code, 409)

    def test_ambiguous_windows_write_requires_reconciliation(self):
        """A timed-out external write cannot be retried automatically."""

        job = self.create_external_write_job()
        claim = self.claim().data["job"]
        response = self.client.post(
            claim["output"]["complete_url"],
            {"status": "failed", "error_code": "BRIDGE_TASK_TIMEOUT"},
            format="multipart",
            secure=True,
            **self.mtls_headers(),
            **self.execution_headers(
                claim["execution_token"], claim["output"]["artifact_token"]
            ),
        )

        job.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(job.error_code, "RECONCILIATION_REQUIRED")
        self.assertFalse(job.retryable)

    def test_external_write_success_wins_a_cancellation_race(self):
        """A confirmed provider result remains success after dispatch cancellation."""

        job = self.create_external_write_job()
        claim = self.claim().data["job"]
        Job.objects.filter(pk=job.pk).update(status=JobStatus.CANCEL_REQUESTED)
        content = b'{"updated":true}'

        response = self.complete(
            claim,
            self.execution_headers(
                claim["execution_token"], claim["output"]["artifact_token"]
            ),
            content,
            hashlib.sha256(content).hexdigest(),
        )

        job.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(job.output_sha256, hashlib.sha256(content).hexdigest())

    def test_external_write_cancel_completion_requires_reconciliation(self):
        """A dispatched remote write cannot claim cancellation erased its side effect."""

        job = self.create_external_write_job()
        claim = self.claim().data["job"]

        response = self.client.post(
            claim["output"]["complete_url"],
            {"status": "cancelled"},
            format="multipart",
            secure=True,
            **self.mtls_headers(),
            **self.execution_headers(
                claim["execution_token"], claim["output"]["artifact_token"]
            ),
        )

        job.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertFalse(job.retryable)

    def test_recovered_claim_fences_old_agent_tokens(self):
        """Recovery rotates execution identity even for the same client certificate."""

        job = self.create_windows_job()
        stale = self.claim().data["job"]
        Job.objects.filter(pk=job.pk).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        current = self.claim().data["job"]
        content = b"{}"

        stale_response = self.complete(
            stale,
            self.execution_headers(
                stale["execution_token"], stale["output"]["artifact_token"]
            ),
            content,
            hashlib.sha256(content).hexdigest(),
        )

        job.refresh_from_db()
        self.assertNotEqual(stale["execution_token"], current["execution_token"])
        self.assertEqual(stale_response.status_code, 409)
        self.assertEqual(job.execution_token.hex, current["execution_token"].replace("-", ""))
        self.assertFalse(job.output_file)

    def test_proxy_spoof_browser_auth_and_cookie_credentials_are_rejected(self):
        """mTLS from a trusted proxy is the sole bridge authentication mechanism."""

        spoofed = self.client.post(
            "/internal/bridge/v1/claims/",
            {},
            format="json",
            secure=True,
            **{**self.mtls_headers(), "REMOTE_ADDR": "198.51.100.20"},
        )
        asserted_only = self.client.post(
            "/internal/bridge/v1/claims/",
            {},
            format="json",
            secure=True,
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_AWC_MTLS_VERIFIED="SUCCESS",
            HTTP_X_AWC_MTLS_FINGERPRINT=FINGERPRINT,
            HTTP_X_AWC_MTLS_SUBJECT=SUBJECT,
        )
        authorized = self.client.post(
            "/internal/bridge/v1/claims/",
            {},
            format="json",
            secure=True,
            **self.mtls_headers(),
            HTTP_AUTHORIZATION="Bearer browser-token",
        )
        cookie = self.client.post(
            "/internal/bridge/v1/claims/",
            {},
            format="json",
            secure=True,
            **self.mtls_headers(),
            HTTP_COOKIE="sessionid=browser-session",
        )
        browser = APIClient()
        browser.force_authenticate(self.user)
        session_only = browser.post(
            "/internal/bridge/v1/claims/", {}, format="json", secure=True
        )
        insecure = self.client.post(
            "/internal/bridge/v1/claims/",
            {},
            format="json",
            secure=False,
            **self.mtls_headers(),
        )
        with override_settings(WINDOWS_BRIDGE_TRUST_PROXY_HEADERS=False):
            untrusted_header_mode = self.client.post(
                "/internal/bridge/v1/claims/",
                {},
                format="json",
                secure=True,
                **self.mtls_headers(),
            )

        self.assertEqual(spoofed.status_code, 403)
        self.assertEqual(asserted_only.status_code, 403)
        self.assertEqual(authorized.status_code, 403)
        self.assertEqual(cookie.status_code, 403)
        self.assertEqual(session_only.status_code, 403)
        self.assertEqual(insecure.status_code, 403)
        self.assertEqual(untrusted_header_mode.status_code, 403)

    def test_status_stays_disabled_until_configured_agent_is_live(self):
        """Configuration alone cannot advertise an unavailable bridge as enabled."""

        browser = APIClient()
        browser.force_authenticate(self.user)
        before = browser.get("/api/integrations/doors/status/")
        idle_claim = self.claim()
        after = browser.get("/api/integrations/doors/status/")
        local_status = browser.get("/api/jobs/system/")
        removed_alias = browser.get("/api/automations/status/")
        with override_settings(WINDOWS_BRIDGE_ENABLED=False):
            disabled = browser.get("/api/integrations/doors/status/")

        self.assertEqual(before.status_code, 200)
        self.assertFalse(before.data["available"])
        self.assertEqual(idle_claim.status_code, 204)
        self.assertTrue(after.data["available"])
        self.assertFalse(local_status.data["available"])
        self.assertEqual(removed_alias.status_code, 404)
        self.assertFalse(disabled.data["available"])

    def create_windows_job(self):
        payload = b'{"operation":"check_module","module_path":"/Project/Module"}'
        job, _ = create_job(
            self.user,
            "doors.run_dxl",
            "Check DOORS module",
            {},
            self.json_upload("doors-operation.json", payload),
        )
        return job

    def create_external_write_job(self):
        job, _ = create_job(
            self.user,
            "doors.update_object",
            "Update DOORS object",
            {},
            self.json_upload("doors-update.json"),
            reconcile_on_lease_loss=True,
        )
        return job

    def claim(self):
        return self.client.post(
            "/internal/bridge/v1/claims/",
            {},
            format="json",
            secure=True,
            **self.mtls_headers(),
        )

    def complete(self, claim, headers, content, digest):
        return self.client.post(
            claim["output"]["complete_url"],
            {
                "status": "succeeded",
                "sha256": digest,
                "output_name": "doors-result.json",
                "file": SimpleUploadedFile(
                    "doors-result.json", content, content_type="application/json"
                ),
            },
            format="multipart",
            secure=True,
            **self.mtls_headers(),
            **headers,
        )

    @staticmethod
    def json_upload(name="input.json", content=b"{}"):
        return SimpleUploadedFile(name, content, content_type="application/json")

    @staticmethod
    def mtls_headers():
        return {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_X_AWC_MTLS_VERIFIED": "SUCCESS",
            "HTTP_X_AWC_MTLS_CERT": CERTIFICATE_HEADER,
        }

    @staticmethod
    def execution_headers(execution_token, artifact_token=None):
        headers = {"HTTP_X_AWC_EXECUTION_TOKEN": execution_token}
        if artifact_token:
            headers["HTTP_X_AWC_ARTIFACT_TOKEN"] = artifact_token
        return headers


class AutomationArchitectureTests(SimpleTestCase):
    """Lock down dependency direction and the static executor catalog."""

    def test_every_catalog_dotted_path_resolves_to_a_callable(self):
        for metadata in EXECUTOR_CATALOG:
            self.assertTrue(callable(import_string(metadata.dotted_path)), metadata.kind)

    def test_local_composition_root_cannot_resolve_windows_executor(self):
        self.assertTrue(executor_kinds(LOCAL_QUEUE))
        self.assertEqual(
            set(executor_kinds(WINDOWS_QUEUE)),
            {
                "doors.run_dxl",
                "doors.update_object",
                "doors.create_object",
                "doors.link_requirements",
            },
        )
        self.assertEqual(set(local_job_kinds()), set(executor_kinds(LOCAL_QUEUE)))
        with self.assertRaises(JobExecutionFailure):
            resolve_job_executor("doors.run_dxl")

    def test_kernel_and_windows_tasks_keep_dependency_direction(self):
        root = Path(__file__).resolve().parents[1]
        kernel_files = tuple((root / "jobs").glob("*.py"))
        feature_roots = {"dcc", "excel", "integrations", "media_tools", "outlook", "word"}
        for path in kernel_files:
            imports = imported_roots(path)
            self.assertTrue(feature_roots.isdisjoint(imports), path.name)

        bridge_imports = imported_roots(
            root / "integrations" / "doors" / "bridge_tasks.py"
        )
        self.assertNotIn("jobs", bridge_imports)
        self.assertNotIn("django.db", bridge_imports)

        composition_source = (root / "awcenter" / "job_executors.py").read_text()
        self.assertNotIn("from dcc", composition_source)
        self.assertNotIn("from integrations", composition_source)
        self.assertNotIn("from word", composition_source)

    def test_jobs_internal_import_graph_is_acyclic(self):
        jobs_root = Path(__file__).resolve().parents[1] / "jobs"
        graph = internal_import_graph(jobs_root)

        self.assertIsNone(find_import_cycle(graph))
        self.assertNotIn("services", graph["workflow_services"])
        self.assertNotIn("services", graph["handoffs"])

    def test_feature_recipes_live_outside_the_jobs_kernel(self):
        root = Path(__file__).resolve().parents[1]

        self.assertTrue((root / "automations" / "recipes.py").is_file())
        self.assertFalse((root / "jobs" / "workflow_recipes.py").exists())
        jobs_urls = (root / "jobs" / "urls.py").read_text(encoding="utf-8")
        self.assertNotIn("retry", jobs_urls)
        self.assertNotIn("handoff", jobs_urls)

    def test_launcher_does_not_supervise_a_windows_server(self):
        root = Path(__file__).resolve().parents[2]
        launcher_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "scripts" / "launcher").glob("*.py")
        ).casefold()
        self.assertNotIn("windows_bridge", launcher_source)
        self.assertNotIn("cheroot", launcher_source)


def imported_roots(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
            imports.add(node.module)
    return imports


def internal_import_graph(package_root):
    modules = {path.stem for path in package_root.glob("*.py") if path.name != "__init__.py"}
    graph = {module: set() for module in modules}
    for module in modules:
        path = package_root / f"{module}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level < 1:
                continue
            if node.module:
                target = node.module.split(".", 1)[0]
                if target in modules:
                    graph[module].add(target)
            else:
                graph[module].update(
                    alias.name for alias in node.names if alias.name in modules
                )
    return graph


def find_import_cycle(graph):
    visited = set()
    active = []

    def visit(node):
        if node in active:
            start = active.index(node)
            return active[start:] + [node]
        if node in visited:
            return None
        active.append(node)
        for target in graph[node]:
            cycle = visit(target)
            if cycle:
                return cycle
        active.pop()
        visited.add(node)
        return None

    for node in graph:
        cycle = visit(node)
        if cycle:
            return cycle
    return None
