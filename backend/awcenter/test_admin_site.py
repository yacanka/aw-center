"""Tests for the canonical AW Center Django admin surface."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse


LEGACY_PROJECT_APP_LABELS = {
    "aesa",
    "blok30",
    "blok4050",
    "gokbey",
    "hys",
    "ozgur",
    "piku",
    "tb2",
}


class CanonicalAdminTests(SimpleTestCase):
    """Keep project data and compliance documents in their canonical apps."""

    def setUp(self):
        user_model = get_user_model()
        self.request = RequestFactory().get("/admin/")
        self.request.user = user_model(is_staff=True, is_superuser=True)

    def test_admin_uses_canonical_organization_and_compliance_apps(self):
        app_list = admin.site.get_app_list(self.request)
        app_labels = {app["app_label"] for app in app_list}

        self.assertIn("orgs", app_labels)
        self.assertIn("compliance", app_labels)
        self.assertTrue(LEGACY_PROJECT_APP_LABELS.isdisjoint(app_labels))

    def test_project_and_role_management_are_exposed_by_orgs(self):
        orgs_app = self._get_app("orgs")
        object_names = {model["object_name"] for model in orgs_app["models"]}

        self.assertIn("Project", object_names)
        self.assertIn("ProjectRoleAssignment", object_names)
        self.assertEqual(orgs_app["app_url"], reverse("admin:app_list", args=("orgs",)))

    def test_compliance_documents_are_exposed_by_compliance(self):
        compliance_app = self._get_app("compliance")
        object_names = {model["object_name"] for model in compliance_app["models"]}

        self.assertIn("ComplianceDocument", object_names)
        self.assertIn("WorkflowEvent", object_names)

    def _get_app(self, app_label):
        return next(
            app
            for app in admin.site.get_app_list(self.request)
            if app["app_label"] == app_label
        )
