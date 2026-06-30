"""Project registry API contract tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .registry import PROJECT_DEFINITIONS

SAFE_RESPONSE_KEYS = {
    "slug",
    "display_name",
    "route",
    "enabled",
    "capabilities",
    "tags",
}
UNSAFE_RESPONSE_KEYS = {
    "app_label",
    "url_prefix",
    "jira_component",
    "dcc_label",
    "dcc_template_name",
    "mail_template_name",
    "dcc_parent_path_setting",
    "filesystem_path",
    "environment_key",
    "mail_address",
}


class ProjectRegistryApiTests(TestCase):
    """Validate the frontend-facing project registry API contract."""

    def setUp(self):
        """Create an authenticated API client for protected registry requests."""
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="registry-user",
            password="safe-test-password",
        )
        self.client.force_authenticate(self.user)

    def test_registry_requires_authentication(self):
        """Unauthenticated callers cannot read project metadata."""
        anonymous_client = APIClient()

        response = anonymous_client.get("/projects/registry/")

        self.assertEqual(response.status_code, 401)

    def test_registry_returns_only_safe_frontend_fields(self):
        """Registry response excludes internal identifiers and integration metadata."""
        response = self.client.get("/projects/registry/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data)
        for project in response.data:
            self.assertEqual(set(project), SAFE_RESPONSE_KEYS)
            self.assertTrue(UNSAFE_RESPONSE_KEYS.isdisjoint(project))

    def test_registry_contract_contains_expected_project_values(self):
        """A registry entry exposes route-oriented metadata without app paths."""
        response = self.client.get("/projects/registry/")
        ozgur_project = self.get_project(response.data, "ozgur")

        self.assertEqual(ozgur_project["display_name"], "Ozgur")
        self.assertEqual(ozgur_project["route"], "/ozgur/")
        self.assertTrue(ozgur_project["enabled"])
        self.assertIn("dcc", ozgur_project["capabilities"])
        self.assertIn("certification", ozgur_project["tags"])

    def test_registry_supports_capability_filter(self):
        """Capability query returns only projects declaring that capability."""
        response = self.client.get("/projects/registry/?capability=dcc")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data)
        for project in response.data:
            self.assertIn("dcc", project["capabilities"])

    def test_registry_supports_enabled_filter(self):
        """Enabled query can return disabled registry entries for UI gating."""
        response = self.client.get("/projects/registry/?enabled=false")
        response_slugs = {project["slug"] for project in response.data}
        disabled_slugs = {
            slug for slug, definition in PROJECT_DEFINITIONS.items() if not definition.enabled
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_slugs, disabled_slugs)

    def test_registry_rejects_invalid_enabled_filter(self):
        """Invalid enabled query values fail closed instead of broadening results."""
        response = self.client.get("/projects/registry/?enabled=maybe")

        self.assertEqual(response.status_code, 400)

    def test_registry_supports_combined_filters(self):
        """Capability and enabled filters compose without leaking unsafe fields."""
        response = self.client.get("/projects/registry/?capability=dcc&enabled=true")

        self.assertEqual(response.status_code, 200)
        for project in response.data:
            self.assertTrue(project["enabled"])
            self.assertIn("dcc", project["capabilities"])
            self.assertEqual(set(project), SAFE_RESPONSE_KEYS)

    def get_project(self, projects, slug):
        """Return one project payload by slug."""
        return next(project for project in projects if project["slug"] == slug)
