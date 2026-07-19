"""Security regression tests for AW Center endpoint exposure."""

from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from projects.registry import get_enabled_project_definitions


APPROVED_PUBLIC_ROUTES = {
    "auth/password-reset/",
    "auth/password-reset/confirm/",
    "auth/token/",
    "auth/invitations/inspect/",
    "auth/invitations/accept/",
    "health/live/",
    "health/ready/",
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
            "/orgs/test/",
            "/doors/test/",
            "/excel/test/",
            "/docproof/test/",
            "/dcc/test/",
            "/dcc/sse_test/",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_rejected_request_returns_support_reference(self):
        """Authentication failures remain traceable from browser to backend logs."""

        response = self.client.get("/orgs/projects/", HTTP_X_REQUEST_ID="browser-123")

        self.assertEqual(response["X-Request-ID"], "browser-123")
        self.assertEqual(response.json()["request_id"], "browser-123")

    @staticmethod
    def _protected_endpoints():
        """Return representative protected endpoints across application domains."""

        endpoints = [
            ("get", "/download/missing.txt/"),
            ("get", "/orgs/projects/"),
            ("get", "/orgs/panels/"),
            ("get", "/orgs/responsibles/"),
            ("get", "/outlook/msg/download/"),
            ("post", "/word/compare/"),
            ("get", "/docproof/search/?document_no=DOC-1"),
        ]
        for project in get_enabled_project_definitions():
            endpoints.extend(project_endpoints(project.url_prefix))
        return endpoints


def project_endpoints(prefix):
    """Return protected document and organization routes for one project."""

    return [
        ("get", f"/{prefix}/compdocs/"),
        ("get", f"/{prefix}/compdocs/fields/"),
        ("get", f"/{prefix}/orgs/panels/"),
        ("get", f"/{prefix}/orgs/responsibles/"),
    ]
