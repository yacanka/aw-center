"""Cross-origin contract tests for authenticated durable operations."""

from django.conf import settings
from django.test import SimpleTestCase


class CorsContractTests(SimpleTestCase):
    """Protect custom headers required by browser job submissions."""

    def test_durable_job_headers_are_preflight_allowlisted(self):
        """Vite and approved split-origin deployments can send idempotent jobs."""

        allowed_headers = {header.lower() for header in settings.CORS_ALLOW_HEADERS}

        self.assertIn("idempotency-key", allowed_headers)
        self.assertIn("x-request-id", allowed_headers)
