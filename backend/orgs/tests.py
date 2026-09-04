"""Organization model, authorization, and project-scoped API tests."""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase
from openpyxl import Workbook
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


class PanelImportApiTests(TestCase):
    """Protect panel workbook mapping, uniqueness, scope, and confirmation."""

    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.manager = get_user_model().objects.create_user("panel-import-manager")
        self.viewer = get_user_model().objects.create_user("panel-import-viewer")
        for user, role in (
            (self.manager, ProjectRoleAssignment.Role.MANAGER),
            (self.viewer, ProjectRoleAssignment.Role.VIEWER),
        ):
            ProjectRoleAssignment.objects.create(
                project=self.project,
                domain=ProjectRoleAssignment.Domain.ORGANIZATION,
                role=role,
                user=user,
            )
        self.existing = Panel.objects.create(
            project=self.project,
            name="Old flight panel",
            discipline="Systems",
            ata="27-00",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    @property
    def preview_url(self):
        return "/api/projects/ozgur/organization/panels/imports/preview/"

    @property
    def confirm_url(self):
        return "/api/projects/ozgur/organization/panels/imports/confirm/"

    @staticmethod
    def workbook(rows, headers=("Panel Name", "ATA Chapter", "Ignored"), title_rows=2):
        workbook = Workbook()
        sheet = workbook.active
        for index in range(title_rows):
            sheet.append([f"Panel inventory {index + 1}"])
        sheet.append(list(headers))
        for row in rows:
            sheet.append(list(row))
        output = BytesIO()
        workbook.save(output)
        return output.getvalue()

    @staticmethod
    def upload(content):
        return SimpleUploadedFile(
            "panels.xlsx",
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def preview(self, content):
        return self.client.post(
            self.preview_url,
            {"file": self.upload(content)},
            format="multipart",
        )

    def confirm(self, content, token):
        return self.client.post(
            self.confirm_url,
            {"file": self.upload(content), "confirmation_token": token},
            format="multipart",
        )

    def test_preview_and_confirm_expand_multiple_ata_values_and_preserve_discipline(self):
        content = self.workbook(
            [("Flight Controls", "27; 28; 29-10", "not imported")],
            headers=("Pannel Name", "ATA Chaptre", "Responsible"),
        )

        preview = self.preview(content)
        confirmed = self.confirm(content, preview.data["confirmation_token"])

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["header_row"], 3)
        self.assertEqual(preview.data["created_count"], 2)
        self.assertEqual(preview.data["updated_count"], 1)
        self.assertEqual(preview.data["unmapped_columns"], ["Responsible"])
        self.assertEqual(confirmed.status_code, 201)
        self.assertEqual(
            list(
                Panel.objects.filter(project=self.project)
                .order_by("ata")
                .values_list("ata", "name")
            ),
            [
                ("27-00", "Flight Controls"),
                ("28-00", "Flight Controls"),
                ("29-10", "Flight Controls"),
            ],
        )
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.discipline, "Systems")

    def test_same_ata_assigned_to_different_panels_is_rejected(self):
        content = self.workbook(
            [("Electrical", "24", ""), ("Avionics", "24-00", "")],
            title_rows=0,
        )

        preview = self.preview(content)

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["created_count"], 0)
        self.assertEqual(preview.data["rejected_count"], 2)
        self.assertFalse(Panel.objects.filter(project=self.project, ata="24-00").exists())

    def test_missing_required_headers_is_rejected_without_writes(self):
        content = self.workbook(
            [("Flight Controls", "27", "")],
            headers=("Panel", "Owner", "Ignored"),
            title_rows=0,
        )

        response = self.preview(content)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "PANEL_IMPORT_COLUMNS_MISSING")
        self.assertIn("ata", response.data["detail"])
        self.assertEqual(Panel.objects.filter(project=self.project).count(), 1)

    def test_viewer_cannot_preview_or_confirm_panel_import(self):
        self.client.force_authenticate(self.viewer)
        content = self.workbook([("Electrical", "24", "")], title_rows=0)

        preview = self.preview(content)
        confirmed = self.confirm(content, "not-a-token")

        self.assertEqual(preview.status_code, 403)
        self.assertEqual(confirmed.status_code, 403)

    def test_confirm_rejects_changed_workbook(self):
        first = self.workbook([("Electrical", "24", "")], title_rows=0)
        second = self.workbook([("Hydraulics", "29", "")], title_rows=0)
        preview = self.preview(first)

        response = self.confirm(second, preview.data["confirmation_token"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "PANEL_IMPORT_PREVIEW_MISMATCH")

    def test_confirm_detects_panel_changes_after_preview(self):
        content = self.workbook([("Electrical", "24", "")], title_rows=0)
        preview = self.preview(content)
        Panel.objects.create(
            project=self.project,
            name="Concurrent panel",
            ata="24-00",
        )

        response = self.confirm(content, preview.data["confirmation_token"])

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "PANEL_IMPORT_VERSION_CONFLICT")
        self.assertEqual(
            Panel.objects.get(project=self.project, ata="24-00").name,
            "Concurrent panel",
        )
