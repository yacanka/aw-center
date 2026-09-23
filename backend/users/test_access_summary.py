"""Project visibility, role resolution and query-count regressions."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.access_policy import effective_role
from orgs.models import Project, ProjectRoleAssignment
from users.serializers import UserAdministrationSerializer, UserSerializer
from users.views import UserView

User = get_user_model()


class ProjectAccessSummaryTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user("s10001", is_staff=True)
        self.actor.user_permissions.add(Permission.objects.get(codename="view_user"))
        self.user = User.objects.create_user("u10001")
        self.group = Group.objects.create(name="Project reviewers")
        self.user.groups.add(self.group)
        self.project = Project.objects.create(name="Summary project", slug="summary-project")
        ProjectRoleAssignment.objects.create(project=self.project, domain="compliance", role="viewer", user=self.user)
        ProjectRoleAssignment.objects.create(project=self.project, domain="compliance", role="manager", group=self.group)
        ProjectRoleAssignment.objects.create(project=self.project, domain="organization", role="viewer", user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.actor)

    def test_admin_sees_strongest_role_and_all_sources(self):
        response = self.client.get(f"/api/users/{self.user.pk}/")
        self.assertEqual(response.status_code, 200)
        access = response.data["project_access"]
        self.assertEqual(len(access), 2)
        self.assertEqual(access[0]["role"], effective_role(self.user, self.project, "compliance"))
        self.assertEqual(access[0]["application"], "Compliance documents")
        self.assertEqual(access[0]["project_slug"], self.project.slug)
        self.assertEqual(access[0]["sources"], [
            {"kind": "direct", "group_id": None, "group_name": None, "role": "viewer"},
            {"kind": "group", "group_id": self.group.pk, "group_name": self.group.name, "role": "manager"},
        ])

    def test_inactive_accounts_and_disabled_projects_keep_assignments(self):
        self.user.is_active = False
        self.user.save()
        self.project.enabled = False
        self.project.save()
        data = self.client.get(f"/api/users/{self.user.pk}/").data
        self.assertFalse(data["is_active"])
        self.assertFalse(data["project_access"][0]["project_enabled"])

    def test_empty_and_superuser_assignments_do_not_fabricate_grants(self):
        self.assertEqual(UserAdministrationSerializer(self.actor).data["project_access"], [])
        self.actor.is_superuser = True
        self.actor.save()
        self.assertTrue(UserAdministrationSerializer(self.actor).data["is_superuser"])
        self.assertEqual(UserAdministrationSerializer(self.actor).data["project_access"], [])

    def test_regular_users_cannot_read_directory_or_details(self):
        self.client.force_authenticate(self.user)
        for path in ("/api/users/", f"/api/users/{self.actor.pk}/"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertNotIn("project_access", UserSerializer(self.user).data)

    def test_prefetched_serialization_does_not_query_per_user(self):
        users = list(UserView()._user_queryset())
        with self.assertNumQueries(0):
            data = UserAdministrationSerializer(users, many=True).data
        self.assertEqual(len(data), 2)

    def test_project_access_is_read_only(self):
        serializer = UserAdministrationSerializer(self.user, data={"project_access": []}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.user.project_role_assignments.count(), 2)
