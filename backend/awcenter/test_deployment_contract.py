import json
from pathlib import Path

import yaml
from django.test import SimpleTestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class DeploymentContractTests(SimpleTestCase):
    """Protect the immutable same-origin production topology."""

    def test_backend_image_builds_and_verifies_frontend_before_runtime(self):
        """The runtime image must contain a verified frontend without Node."""

        dockerfile = self.read("backend/Dockerfile")
        frontend_stage = dockerfile.index("FROM node:22-alpine AS frontend-build")
        runtime_stage = dockerfile.index("FROM python:3.14-slim AS runtime")

        self.assertLess(frontend_stage, runtime_stage)
        self.assertIn("RUN npm ci", dockerfile[:runtime_stage])
        self.assertIn("COPY --from=frontend-build /frontend/dist /app/frontend-dist", dockerfile)
        self.assertIn("python manage.py collectstatic --noinput", dockerfile)
        self.assertIn("python manage.py verify_frontend_artifact", dockerfile)
        self.assertNotIn("node:22", dockerfile[runtime_stage:])

    def test_compose_uses_one_origin_without_masking_image_static_files(self):
        """Compose must expose Django's SPA and API through one service."""

        compose = yaml.safe_load(self.read("docker-compose.yml"))
        backend = compose["services"]["backend"]

        self.assertNotIn("frontend", compose["services"])
        self.assertEqual(backend["ports"], ["8080:8000"])
        self.assertEqual(backend["build"]["args"]["VITE_API_URL"], "/")
        self.assertNotIn("backend-static", compose["volumes"])
        self.assertNotIn("/app/static", " ".join(backend.get("volumes", [])))

    def test_ci_uses_strict_read_only_and_container_quality_gates(self):
        """CI cannot mutate sources or bypass type and artifact checks."""

        workflow = self.read(".github/workflows/ci.yml")

        self.assertNotIn("npm run format\n", workflow)
        self.assertNotIn("--noCheck", workflow)
        self.assertGreaterEqual(workflow.count("npm ci"), 2)
        self.assertIn("makemigrations --check --dry-run", workflow)
        self.assertIn("python manage.py verify_frontend_artifact", workflow)
        self.assertIn("docker build", workflow)
        self.assertIn("docker run --rm", workflow)

        launcher = self.read("launcher.py")
        self.assertNotIn('"typecheck:ci"', launcher)

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

    def read(self, relative_path):
        """Read one bounded repository deployment file."""

        return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
