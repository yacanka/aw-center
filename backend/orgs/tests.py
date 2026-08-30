"""Organization model, authorization, and project-scoped API tests."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from .access_policy import effective_role, has_role_for_all_projects
from .models import (
    Panel,
    Person,
    Project,
    ProjectRoleAssignment,
    ResponsibleAssignment,
)


class ProjectRolePolicyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("role-user")
        self.project = Project.objects.get(slug="ozgur")

    def test_highest_direct_or_group_role_is_effective(self):
        group = Group.objects.create(name="Managers")
        group.user_set.add(self.user)
        ProjectRoleAssignment.objects.create(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.VIEWER,
            user=self.user,
        )
        ProjectRoleAssignment.objects.create(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.MANAGER,
            group=group,
        )

        self.assertEqual(
            effective_role(
                self.user,
                self.project,
                ProjectRoleAssignment.Domain.COMPLIANCE,
            ),
            ProjectRoleAssignment.Role.MANAGER,
        )

    def test_assignment_accepts_exactly_one_subject_and_valid_domain_role(self):
        assignment = ProjectRoleAssignment(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.ORGANIZATION,
            role=ProjectRoleAssignment.Role.OPERATOR,
            user=self.user,
        )
        with self.assertRaises(ValidationError):
            assignment.full_clean()

        assignment.role = ProjectRoleAssignment.Role.MANAGER
        assignment.group = Group.objects.create(name="invalid-second-subject")
        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_multi_project_role_requires_every_related_project(self):
        second = Project.objects.get(slug="piku")
        ProjectRoleAssignment.objects.create(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.DCC,
            role=ProjectRoleAssignment.Role.OPERATOR,
            user=self.user,
        )

        self.assertFalse(
            has_role_for_all_projects(
                self.user,
                [self.project, second],
                ProjectRoleAssignment.Domain.DCC,
                ProjectRoleAssignment.Role.OPERATOR,
            )
        )


class OrganizationApiTests(TestCase):
    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.viewer = get_user_model().objects.create_user("org-viewer")
        self.manager = get_user_model().objects.create_user("org-manager")
        ProjectRoleAssignment.objects.create(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.ORGANIZATION,
            role=ProjectRoleAssignment.Role.VIEWER,
            user=self.viewer,
        )
        ProjectRoleAssignment.objects.create(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.ORGANIZATION,
            role=ProjectRoleAssignment.Role.MANAGER,
            user=self.manager,
        )
        permission = Permission.objects.get(codename="manage_people_directory")
        self.manager.user_permissions.add(permission)
        self.panel = Panel.objects.create(
            project=self.project,
            name="Flight",
            discipline="Systems",
            ata="27-00",
        )
        self.person = Person.objects.create(
            person_id="100001",
            name="Ada Engineer",
            email="ada@example.com",
        )
        self.client = APIClient()

    @property
    def root(self):
        return "/api/projects/ozgur/organization/"

    def test_viewer_reads_project_assignments_but_cannot_mutate(self):
        ResponsibleAssignment.objects.create(
            panel=self.panel,
            person=self.person,
            responsibility_role="AS",
        )
        self.client.force_authenticate(self.viewer)

        listed = self.client.get(
            f"{self.root}responsible-assignments/?panel=27-00"
        )
        rejected = self.client.post(
            f"{self.root}panels/",
            {"name": "New", "discipline": "Systems", "ata": "28-00"},
            format="json",
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(rejected.status_code, 403)

    def test_manager_with_global_permission_updates_people_directory(self):
        self.client.force_authenticate(self.manager)

        response = self.client.patch(
            f"{self.root}people/{self.person.pk}/",
            {"name": "Ada Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.person.refresh_from_db()
        self.assertEqual(self.person.name, "Ada Updated")

    def test_project_manager_without_global_permission_cannot_update_people(self):
        manager = get_user_model().objects.create_user("project-only-manager")
        ProjectRoleAssignment.objects.create(
            project=self.project,
            domain=ProjectRoleAssignment.Domain.ORGANIZATION,
            role=ProjectRoleAssignment.Role.MANAGER,
            user=manager,
        )
        self.client.force_authenticate(manager)

        response = self.client.patch(
            f"{self.root}people/{self.person.pk}/",
            {"name": "Unauthorized"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.person.refresh_from_db()
        self.assertEqual(self.person.name, "Ada Engineer")
