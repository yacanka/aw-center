import json
from pathlib import Path

import yaml
from django.test import SimpleTestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class DeploymentContractTests(SimpleTestCase):
    """Protect the immutable same-origin production topology."""

    def test_docker_context_excludes_workstation_generated_and_secret_state(self):
        """Local ignored artifacts cannot alter or leak into a release image build."""

        ignored = {
            line.strip()
            for line in self.read(".dockerignore").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        required = {
            ".runtime/",
            ".env",
            ".env.*",
            "backend/.env*",
            "frontend/.env*",
            "backend/static/",
            "backend/staticfiles/",
            "frontend/test-results/",
            "frontend/playwright-report/",
            "release-metadata/",
            "image-build-metadata.json",
            "image-frontend-dist/",
        }

        self.assertTrue(required.issubset(ignored), required - ignored)

    def test_backend_image_builds_and_verifies_frontend_before_runtime(self):
        """The runtime image must contain a verified frontend without Node."""

        dockerfile = self.read("backend/Dockerfile")
        frontend_stage = dockerfile.index("FROM node:22-alpine@sha256:")
        runtime_stage = dockerfile.index("FROM python:3.11-slim@sha256:", frontend_stage)
        runtime_stage = dockerfile.index("FROM python:3.11-slim@sha256:", runtime_stage + 1)

        self.assertLess(frontend_stage, runtime_stage)
        self.assertIn("RUN npm ci", dockerfile[:runtime_stage])
        self.assertIn("COPY --from=frontend-build /frontend/dist /app/frontend-dist", dockerfile)
        self.assertIn("python manage.py collectstatic --clear --noinput", dockerfile)
        self.assertIn("python manage.py verify_frontend_artifact", dockerfile)
        self.assertIn("/app/ai-models", dockerfile)
        self.assertIn("/app/document-templates", dockerfile)
        self.assertIn("chmod -R a-w /app", dockerfile)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertNotIn("chown -R awcenter:awcenter /app\n", dockerfile)
        self.assertNotIn("node:22", dockerfile[runtime_stage:])
        self.assertNotIn("build-essential", dockerfile[runtime_stage:])
        self.assertNotIn("pip install --upgrade pip", dockerfile)
        for line in dockerfile.splitlines():
            if line.startswith("FROM "):
                self.assertIn("@sha256:", line)

    def test_compose_uses_one_origin_without_masking_image_static_files(self):
        """Compose must expose Django's SPA and API through one service."""

        compose = yaml.safe_load(self.read("docker-compose.yml"))
        services = compose["services"]
        backend = services["backend"]

        self.assertNotIn("frontend", compose["services"])
        self.assertEqual(
            services["ingress"]["ports"],
            ["80:80", "443:443", "127.0.0.1:${DOORS_RUNNER_PORT:-8765}:8765"],
        )
        self.assertNotIn("ports", backend)
        self.assertNotIn("build", backend)
        self.assertIn("AWCENTER_IMAGE", backend["image"])
        self.assertIn("immutable digest", backend["image"])
        self.assertNotIn("backend-static", compose["volumes"])
        self.assertNotIn("/app/static", " ".join(backend.get("volumes", [])))
        rendered = self.read("docker-compose.yml")
        self.assertIn("${SECRET_KEY:?", rendered)
        self.assertIn("${DATABASE_URL:?", rendered)
        self.assertNotIn("change-me-local-only", rendered)
        self.assertIn(
            "/etc/nginx/templates/default.conf.template:ro",
            " ".join(services["ingress"]["volumes"]),
        )
        self.assertNotIn("windows-bridge-ingress", services)
        for name in ("ingress", "database", "redis"):
            self.assertIn("@sha256:", services[name]["image"])
        for name in ("backend", "worker", "notification-worker", "cleanup-worker"):
            self.assertEqual(services[name]["user"], "10001:10001")
            self.assertEqual(services[name]["cap_drop"], ["ALL"])
            self.assertIn("no-new-privileges:true", services[name]["security_opt"])

    def test_compose_supervises_each_background_lifecycle_with_health(self):
        """Execution, notification, and retention responsibilities stay independent."""

        compose = yaml.safe_load(self.read("docker-compose.yml"))
        services = compose["services"]

        for name in ("worker", "notification-worker", "cleanup-worker"):
            service = services[name]
            self.assertEqual(service["restart"], "unless-stopped")
            self.assertIn("healthcheck", service)
            self.assertTrue(service["init"])
        self.assertIn("run_job_worker", services["worker"]["command"])
        self.assertIn(
            "run_compdoc_notification_worker", services["notification-worker"]["command"]
        )
        self.assertIn("run_job_cleanup_worker", services["cleanup-worker"]["command"])
        self.assertIn("private-artifacts:/app/private_media", services["cleanup-worker"]["volumes"])
        self.assertIn("--heartbeat-file", services["notification-worker"]["command"])
        self.assertEqual(services["notification-worker"]["volumes"], [])
        self.assertNotIn(
            "JIRA_SESSION_ENCRYPTION_KEY",
            services["notification-worker"]["environment"],
        )
        self.assertNotIn(
            "TEAMCENTER_PASSWORD",
            services["cleanup-worker"]["environment"],
        )
        self.assertNotIn(
            "EMAIL_HOST_PASSWORD",
            services["worker"]["environment"],
        )
        self.assertNotIn(
            "EMAIL_HOST_PASSWORD",
            services["backend"]["environment"],
        )
        for service_name in ("backend", "worker"):
            service = services[service_name]
            volumes = " ".join(service["volumes"])
            self.assertIn("/app/ai-models:ro", volumes)
            self.assertIn("/app/document-templates:ro", volumes)
            self.assertNotIn("/app/models", volumes)
            self.assertEqual(
                service["environment"]["MODEL_RUNTIME_DIR"],
                "/app/ai-models",
            )
            self.assertEqual(
                service["environment"]["CUSTOM_TEMPLATE_DIR"],
                "/app/document-templates",
            )
        self.assertEqual(services["redis"]["user"], "redis")
        self.assertIn("requirepass %s", " ".join(services["redis"]["command"]))
        self.assertNotIn("--requirepass", services["redis"]["command"][-1])
        self.assertIn("unset REDIS_PASSWORD", services["redis"]["command"][-1])
        self.assertIn("DOORS_RUNNER_TOKEN", services["backend"]["environment"])

    def test_ci_uses_strict_read_only_and_container_quality_gates(self):
        """CI cannot mutate sources or bypass type and artifact checks."""

        workflow = self.read(".github/workflows/ci.yml")

        self.assertNotIn("npm run format\n", workflow)
        self.assertNotIn("--noCheck", workflow)
        self.assertGreaterEqual(workflow.count("npm ci"), 2)
        self.assertIn("npx playwright install --with-deps chromium", workflow)
        self.assertIn("npm run test:e2e", workflow)
        self.assertIn("makemigrations --check --dry-run", workflow)
        self.assertIn("python manage.py verify_frontend_artifact", workflow)
        self.assertIn("docker build", workflow)
        self.assertIn("docker run --rm", workflow)
        self.assertIn('python-version: "3.11"', workflow)
        self.assertIn('python-version: "3.14"', workflow)
        self.assertIn("postgres:17-alpine", workflow)
        self.assertIn("redis:7-alpine", workflow)
        self.assertIn("build_release_metadata.py", workflow)
        self.assertIn("verify_release_image.py", workflow)
        self.assertIn("deployment_preflight.py", workflow)
        self.assertIn("--release-manifest", workflow)
        self.assertIn("--image-verification", workflow)
        self.assertIn("--sbom=true", workflow)
        self.assertIn(
            "python -m unittest scripts.test_launcher scripts.test_launcher_jobs scripts.test_release_metadata",
            workflow,
        )
        self.assertIn("not os.access('/app/manage.py', os.W_OK)", workflow)
        self.assertIn('JIRA_ENABLED: "False"', workflow)
        self.assertNotIn("JIRA_LEGACY_URL", workflow)
        self.assertNotIn("JIRA_BTB_URL", workflow)
        for line in workflow.splitlines():
            stripped = line.strip()
            if stripped.startswith("uses: actions/"):
                action = stripped.split("#", 1)[0].rstrip()
                self.assertRegex(action, r"@[0-9a-f]{40}$")

        launcher = self.read("launcher.py")
        self.assertNotIn('"typecheck:ci"', launcher)
        runtime = self.read("scripts/launcher/runtime.py")
        parser = self.read("scripts/launcher/parser.py")
        self.assertNotIn("def prod(", runtime)
        self.assertNotIn('add_parser("prod"', parser)

    def test_root_npm_manifest_is_dependency_free_strict_proxy(self):
        """Root npm commands cannot use stale dependencies or bypass frontend gates."""

        manifest = json.loads(self.read("package.json"))
        scripts = manifest["scripts"]

        self.assertTrue(manifest["private"])
        self.assertNotIn("dependencies", manifest)
        self.assertNotIn("devDependencies", manifest)
        self.assertNotIn("typecheck:ci", scripts)
        self.assertNotIn("deploy", scripts)
        self.assertTrue(all("--prefix frontend" in command for command in scripts.values()))

    def test_nginx_rejects_public_media_and_matches_backend_upload_ceiling(self):
        """The reverse proxy cannot expose media or reject backend-approved uploads early."""

        nginx = self.read("deploy/nginx/awcenter.conf")
        media_start = nginx.index("location ^~ /media/")
        media_end = nginx.index("location ^~ /internal/", media_start)
        media_block = nginx[media_start:media_end]

        self.assertIn("client_max_body_size 600m;", nginx)
        self.assertIn("return 404;", media_block)
        self.assertNotIn("proxy_pass", media_block)
        self.assertIn("listen 443 ssl", nginx)
        self.assertIn("listen 127.0.0.1:8080", nginx)
        self.assertIn("return 308 https://${AWCENTER_HOST}$request_uri;", nginx)
        self.assertIn('"$request_method $uri $server_protocol"', nginx)
        self.assertIn("access_log /var/log/nginx/access.log awcenter_safe;", nginx)
        self.assertIn("listen 8765;", nginx)
        self.assertIn("location ^~ /internal/doors-runner/v1/", nginx)
        self.assertIn('proxy_set_header Authorization "";', nginx)
        self.assertIn('proxy_set_header Cookie "";', nginx)
        self.assertFalse((REPOSITORY_ROOT / "deploy/nginx/windows-bridge.conf").exists())

    def read(self, relative_path):
        """Read one bounded repository deployment file."""

        return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
