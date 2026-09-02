"""Security regression tests for AW Center endpoint exposure."""

from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

APPROVED_PUBLIC_ROUTES = {
    "api/session/",
    "api/users/password-reset/",
    "api/users/password-reset/confirm/",
    "api/users/invitations/inspect/",
    "api/users/invitations/accept/",
    "health/live/",
    "health/ready/",
    # These routes deliberately bypass browser authentication; the views require
    # the dedicated token available only to the host-local DOORS runner.
    "internal/doors-runner/v1/claims/",
    "internal/doors-runner/v1/jobs/<uuid:job_id>/complete/",
    "internal/doors-runner/v1/jobs/<uuid:job_id>/heartbeat/",
    "internal/doors-runner/v1/jobs/<uuid:job_id>/input/",
    "internal/doors-runner/v1/status/",
}


def collect_allow_any_routes(patterns, prefix=""):
    """Return concrete URL routes that explicitly allow anonymous access."""

    routes = set()
    for pattern in patterns:
        route = f"{prefix}{pattern.pattern}"
        if isinstance(pattern, URLResolver):
            routes.update(collect_allow_any_routes(pattern.url_patterns, route))
        elif isinstance(pattern, URLPattern) and allows_anonymous(pattern.callback):
            routes.add(route)
    return routes


def allows_anonymous(callback):
    """Return whether a DRF callback explicitly declares AllowAny."""

    view_class = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    permission_classes = getattr(view_class, "permission_classes", ())
    return AllowAny in permission_classes


class EndpointSecurityTests(SimpleTestCase):
    """Keep business endpoints deny-by-default before production release."""

    def setUp(self):
        """Create an unauthenticated API client."""

        self.client = APIClient()

    def test_only_approved_routes_allow_anonymous_access(self):
        """New AllowAny declarations require an explicit security decision."""

        public_routes = collect_allow_any_routes(get_resolver().url_patterns)

        self.assertEqual(public_routes, APPROVED_PUBLIC_ROUTES)

    def test_business_endpoints_reject_anonymous_requests(self):
        """Core document, organization, and integration APIs require login."""

        endpoints = self._protected_endpoints()
        for method, path in endpoints:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, {}, format="json")
                self.assertIn(response.status_code, {401, 403})

    def test_development_probe_routes_are_not_deployed(self):
        """Placeholder probe endpoints stay absent from the production surface."""

        paths = [
            "/api/orgs/test/",
            "/api/integrations/doors/test/",
            "/api/tools/excel/test/",
            "/api/integrations/docproof/test/",
            "/api/dcc/test/",
            "/api/dcc/sse_test/",
            "/core/views.py",
            "/core/__pycache__/views.pyc",
            "/media/private.txt",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_rejected_request_returns_support_reference(self):
        """Authentication failures remain traceable from browser to backend logs."""

        response = self.client.get("/api/projects/", HTTP_X_REQUEST_ID="browser-123")

        self.assertEqual(response["X-Request-ID"], "browser-123")
        self.assertEqual(response.json()["request_id"], "browser-123")

    @staticmethod
    def _protected_endpoints():
        """Return representative protected endpoints across application domains."""

        endpoints = [
            ("get", "/api/projects/"),
            ("get", "/api/projects/aesa/organization/panels/"),
            ("get", "/api/projects/aesa/organization/responsible-assignments/"),
            ("get", "/api/tools/outlook/msg/download/"),
            ("post", "/api/tools/word/compare/"),
            ("get", "/api/integrations/docproof/search/?document_no=DOC-1"),
            ("get", "/api/dcc/records/"),
            ("get", "/api/jobs/00000000-0000-0000-0000-000000000001/"),
        ]
        endpoints.extend(project_endpoints("aesa"))
        return endpoints


def project_endpoints(slug):
    """Return protected document and organization routes for one project."""

    document_id = "00000000-0000-0000-0000-000000000001"
    return [
        ("get", f"/api/projects/{slug}/compliance-documents/"),
        ("get", f"/api/projects/{slug}/compliance-documents/fields/"),
        ("get", f"/api/projects/{slug}/compliance-documents/notification-policy/"),
        ("put", f"/api/projects/{slug}/compliance-documents/notification-policy/"),
        ("get", f"/api/projects/{slug}/compliance-documents/{document_id}/tracking/"),
        ("get", f"/api/projects/{slug}/organization/panels/"),
        ("get", f"/api/projects/{slug}/organization/responsible-assignments/"),
    ]
