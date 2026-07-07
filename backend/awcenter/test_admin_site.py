"""Tests for AW Center Django admin site behavior."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from awcenter.admin import PROJECTS_ADMIN_APP_LABEL


class ProjectAdminGroupingTests(SimpleTestCase):
    """Verify project models are displayed under one admin section."""

    def setUp(self):
        """Create a staff superuser request for admin app-list checks."""
        user_model = get_user_model()
        self.request = RequestFactory().get('/admin/')
        self.request.user = user_model(is_staff=True, is_superuser=True)

    def test_project_apps_are_grouped_under_projects(self):
        """Project-specific apps are hidden behind one Projects section."""
        app_list = admin.site.get_app_list(self.request)
        app_labels = {app['app_label'] for app in app_list}
        projects_app = self._get_projects_app(app_list)
        model_names = {model['name'] for model in projects_app['models']}

        self.assertIn(PROJECTS_ADMIN_APP_LABEL, app_labels)
        self.assertNotIn('aesa', app_labels)
        self.assertNotIn('ozgur', app_labels)
        self.assertIn('Aesa Comp docs', model_names)
        self.assertIn('Ozgur Comp docs', model_names)

    def test_projects_app_index_returns_only_projects_section(self):
        """Synthetic Projects admin index returns grouped project models only."""
        projects_app_list = admin.site.get_app_list(
            self.request, app_label=PROJECTS_ADMIN_APP_LABEL
        )

        self.assertEqual(len(projects_app_list), 1)
        self.assertEqual(projects_app_list[0]['app_label'], PROJECTS_ADMIN_APP_LABEL)
        self.assertTrue(projects_app_list[0]['models'])

    def test_projects_app_url_is_reversible(self):
        """Projects admin section has a dedicated synthetic app URL."""
        projects_app = self._get_projects_app(admin.site.get_app_list(self.request))

        self.assertEqual(projects_app['app_url'], reverse('admin:projects_app_list'))

    def _get_projects_app(self, app_list):
        """Return the synthetic Projects app from an admin app list."""
        return next(
            app for app in app_list if app['app_label'] == PROJECTS_ADMIN_APP_LABEL
        )
