"""Development reset authorization, atomicity and scope regressions."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from orgs.models import Panel, Person, Project, ProjectRoleAssignment, ResponsibleAssignment
from .developer import RESET_PHRASE
from .models import ComplianceDocument, CoverPage


@override_settings(DEBUG=True, AWCENTER_DEPLOYMENT_MODE="development")
class DeveloperResetTests(TestCase):
    url = "/api/developer/compliance-organization-reset/"

    def setUp(self):
        self.user = get_user_model().objects.create_superuser("reset-admin", password="test-only")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.project = Project.objects.get(slug="ozgur")
        self.panel = Panel.objects.create(project=self.project, name="Panel", ata="27-00")
        self.person = Person.objects.create(person_id="test-person", name="Test", email="test@example.invalid")
        ResponsibleAssignment.objects.create(panel=self.panel, person=self.person, responsibility_role="AS")
        self.cover = CoverPage.objects.create(project=self.project, number="CP-TEST")
        self.document = ComplianceDocument.objects.create(project=self.project, panel=self.panel, cover_page=self.cover, name="Test")

    def payload(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return {"confirmation_phrase": RESET_PHRASE, "confirmation_token": response.data["confirmation_token"]}

    def test_reset_clears_protected_relations_and_history_preserving_catalog_accounts_and_dcc_roles(self):
        ProjectRoleAssignment.objects.create(project=self.project, user=self.user, domain="dcc", role="viewer")
        ProjectRoleAssignment.objects.create(project=self.project, user=self.user, domain="compliance", role="manager")
        response = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        for model in [ComplianceDocument, CoverPage, Panel, Person, ResponsibleAssignment]:
            self.assertFalse(model.objects.exists(), model.__name__)
        self.assertFalse(ComplianceDocument.history.exists())
        self.assertFalse(CoverPage.history.exists())
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertEqual(list(ProjectRoleAssignment.objects.values_list("domain", flat=True)), ["dcc"])

    @override_settings(DEBUG=False)
    def test_production_is_disabled_for_superuser(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 404)
        self.assertTrue(ComplianceDocument.objects.exists())

    def test_staff_and_anonymous_are_denied(self):
        self.user.is_superuser = False
        self.user.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_confirmation_required_and_stale_preview_rejected(self):
        payload = self.payload()
        self.assertEqual(self.client.post(self.url, {**payload, "confirmation_phrase": "wrong"}, format="json").status_code, 400)
        Person.objects.create(person_id="another", name="Other", email="other@example.invalid")
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        self.assertTrue(ComplianceDocument.objects.exists())

    def test_invalid_and_expired_tokens_rejected(self):
        payload = self.payload()
        self.assertEqual(self.client.post(self.url, {**payload, "confirmation_token": "invalid"}, format="json").status_code, 400)
        with patch("django.core.signing.time.time", return_value=9999999999):
            self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)

    def test_active_jobs_block_reset(self):
        with patch("compliance.developer.Job.objects") as jobs:
            jobs.exclude.return_value.exists.return_value = True
            response = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ComplianceDocument.objects.exists())

    def test_session_post_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.payload(), format="json").status_code, 403)

    @override_settings(AWCENTER_DEPLOYMENT_MODE="windows-native")
    def test_production_profile_is_disabled_even_with_debug(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_preview_is_bound_to_user(self):
        payload = self.payload()
        other = get_user_model().objects.create_superuser("other-admin")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 403)
        self.assertTrue(ComplianceDocument.objects.exists())

    def test_protected_dependency_rolls_back_prior_deletions(self):
        from django.db.models.query import QuerySet
        original_delete = QuerySet.delete

        def delete(queryset):
            if queryset.model is Person:
                raise ProtectedError("Test dependency", [self.person])
            return original_delete(queryset)

        payload = self.payload()
        with patch.object(QuerySet, "delete", delete):
            response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ComplianceDocument.objects.filter(pk=self.document.pk).exists())
        self.assertTrue(CoverPage.objects.filter(pk=self.cover.pk).exists())
        self.assertTrue(ResponsibleAssignment.objects.exists())
