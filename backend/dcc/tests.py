"""Canonical DCC record and route contract tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment

from .models import DccRecord


class DccRecordApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user("dcc-owner")
        self.assignee = user_model.objects.create_user("dcc-assignee")
        self.outsider = user_model.objects.create_user("dcc-outsider")
        self.first = Project.objects.get(slug="hys")
        self.second = Project.objects.get(slug="gokbey")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def grant(self, user, project, role):
        return ProjectRoleAssignment.objects.create(
            user=user,
            project=project,
            domain=ProjectRoleAssignment.Domain.DCC,
            role=role,
        )

    def grant_all(self, user, role):
        self.grant(user, self.first, role)
        self.grant(user, self.second, role)

    def create_record(self):
        self.grant_all(self.owner, ProjectRoleAssignment.Role.OPERATOR)
        response = self.client.post(
            "/api/dcc/records/",
            {
                "issue": "DCC-42",
                "title": "Canonical record",
                "project_slugs": [self.first.slug, self.second.slug],
                "assigned_users": [self.assignee.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return response

    def test_record_is_uuid_project_scoped_and_has_no_filesystem_contract(self):
        response = self.create_record()

        self.assertEqual(
            set(response.data["project_slugs"]),
            {self.first.slug, self.second.slug},
        )
        self.assertNotIn("projects", response.data)
        self.assertNotIn("dcc_path", response.data)
        self.assertNotIn("ecd_name", response.data)
        record = DccRecord.objects.get(pk=response.data["id"])
        self.assertEqual(record.owner, self.owner)

    def test_assigned_viewer_must_hold_role_for_every_project(self):
        response = self.create_record()
        detail_url = f"/api/dcc/records/{response.data['id']}/"
        self.grant(self.assignee, self.first, ProjectRoleAssignment.Role.VIEWER)
        self.client.force_authenticate(self.assignee)

        blocked = self.client.get(detail_url)
        self.grant(self.assignee, self.second, ProjectRoleAssignment.Role.VIEWER)
        allowed = self.client.get(detail_url)

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(allowed.status_code, 200)

    def test_assigned_operator_can_version_checked_update_and_delete(self):
        response = self.create_record()
        self.grant_all(self.assignee, ProjectRoleAssignment.Role.OPERATOR)
        self.client.force_authenticate(self.assignee)
        detail_url = f"/api/dcc/records/{response.data['id']}/"

        updated = self.client.patch(
            detail_url,
            {"title": "Updated", "version": response.data["version"]},
            format="json",
        )
        stale = self.client.patch(
            detail_url,
            {"title": "Stale", "version": response.data["version"]},
            format="json",
        )
        deleted = self.client.delete(
            detail_url,
            {"version": updated.data["version"]},
            format="json",
        )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(deleted.status_code, 204)

    def test_owner_without_operator_on_every_project_cannot_create(self):
        self.grant(self.owner, self.first, ProjectRoleAssignment.Role.OPERATOR)
        response = self.client.post(
            "/api/dcc/records/",
            {
                "issue": "DCC-43",
                "title": "Blocked",
                "project_slugs": [self.first.slug, self.second.slug],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(DccRecord.objects.exists())

    def test_projectless_record_fails_closed_even_for_its_owner(self):
        record = DccRecord.objects.create(
            issue="DCC-44",
            title="Invalid legacy row",
            owner=self.owner,
        )

        response = self.client.get(f"/api/dcc/records/{record.id}/")

        self.assertEqual(response.status_code, 403)

    def test_superuser_bypasses_roles_but_not_projectless_fail_closed(self):
        superuser = type(self.owner).objects.create_superuser("dcc-admin")
        scoped = DccRecord.objects.create(
            issue="DCC-45",
            title="Scoped",
            owner=self.owner,
        )
        scoped.projects.add(self.first)
        projectless = DccRecord.objects.create(
            issue="DCC-46",
            title="Projectless",
            owner=self.owner,
        )
        self.client.force_authenticate(superuser)

        allowed = self.client.get(f"/api/dcc/records/{scoped.id}/")
        blocked = self.client.get(f"/api/dcc/records/{projectless.id}/")

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(blocked.status_code, 403)


class DccLegacyRouteAbsenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("route-owner")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_legacy_direct_write_and_credential_routes_are_absent(self):
        for path in (
            "api/",
            "add/",
            "get_issue/",
            "create_issue/",
            "send_mail/",
            "upload/",
            "add_attachment/",
            "check_session/",
            "ecd_assessment/",
            "events/",
        ):
            with self.subTest(path=path):
                response = self.client.post(f"/api/dcc/{path}", {}, format="json")
                self.assertEqual(response.status_code, 404)
