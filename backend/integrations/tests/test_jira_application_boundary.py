"""JIRA application identities must follow the integrations boundary."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib import admin
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient


class JiraApplicationBoundaryTests(TestCase):
    def test_jira_models_remain_available_in_admin(self):
        for name in ("JiraTrackedIssue", "JiraReminderDelivery", "JiraIssueDraft", "JiraIssueDraftEvent"):
            self.assertTrue(admin.site.is_registered(apps.get_model("integrations", name)), name)

    def test_tracking_assignment_inlines_keep_parent_change_permissions(self):
        user = get_user_model().objects.create_user("admin-boundary", is_staff=True)
        user.user_permissions.add(Permission.objects.get(content_type__app_label="integrations", codename="change_jiratrackedissue"))
        request = RequestFactory().get("/admin/")
        request.user = user
        model = apps.get_model("integrations", "JiraTrackedIssue")
        model_admin = admin.site._registry[model]
        inlines = model_admin.get_inline_instances(request)
        self.assertEqual(len(inlines), 2)
        self.assertTrue(all(inline.has_change_permission(request) for inline in inlines))

    def test_tracking_models_are_owned_by_integrations(self):
        models = apps.all_models["integrations"]
        self.assertIsNotNone(models.get("jiratrackedissue"))
        self.assertIsNotNone(models.get("jirareminderdelivery"))
        self.assertIsNotNone(models.get("jiraissuedraft"))
        self.assertEqual(list(apps.get_app_config("dcc").get_models()), [])

    def test_canonical_watcher_route_is_under_jira_integration(self):
        user = get_user_model().objects.create_user("boundary-user")
        client = APIClient()
        client.force_authenticate(user)
        response = client.get("/api/integrations/jira/watcher/preferences/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"outstanding_only": False, "detail_fields": {}, "component_fields": {}})
        self.assertEqual(client.get("/api/dcc/watcher/preferences/").status_code, 404)
