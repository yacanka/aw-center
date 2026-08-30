"""User-visible project catalog contract tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment


SAFE_KEYS = {"slug", "name", "capabilities", "roles"}


class ProjectRegistryApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user("registry-user")
        self.ozgur = Project.objects.get(slug="ozgur")

    def test_catalog_requires_authentication_and_has_no_static_fallback(self):
        anonymous = self.client.get("/api/projects/")
        self.client.force_authenticate(self.user)
        empty = self.client.get("/api/projects/")

        self.assertIn(anonymous.status_code, {401, 403})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data, [])

    def test_catalog_joins_enabled_business_record_roles_and_capabilities(self):
        ProjectRoleAssignment.objects.create(
            project=self.ozgur,
            domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.EDITOR,
            user=self.user,
        )
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        project = response.data[0]
        self.assertEqual(set(project), SAFE_KEYS)
        self.assertEqual(project["slug"], "ozgur")
        self.assertEqual(project["roles"]["compliance"], "editor")
        self.assertIsNone(project["roles"]["dcc"])
        self.assertNotIn("jira_component", project)

    def test_disabled_or_unknown_projects_are_hidden(self):
        ProjectRoleAssignment.objects.create(
            project=self.ozgur,
            domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.VIEWER,
            user=self.user,
        )
        self.ozgur.enabled = False
        self.ozgur.save(update_fields=["enabled"])
        unknown = Project.objects.create(slug="unknown", name="Unknown", enabled=True)
        ProjectRoleAssignment.objects.create(
            project=unknown,
            domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.VIEWER,
            user=self.user,
        )
        self.client.force_authenticate(self.user)

        self.assertEqual(self.client.get("/api/projects/").data, [])
