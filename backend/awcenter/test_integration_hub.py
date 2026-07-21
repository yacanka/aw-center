"""Tests for the non-secret integration capability catalog."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch


class IntegrationHubTests(TestCase):
    """Verify safe integration discovery for authenticated users."""

    def setUp(self):
        """Create an authenticated API client."""

        self.client = APIClient()
        self.user = get_user_model().objects.create_user("bridge-user", password="pass")

    def test_anonymous_user_cannot_discover_integrations(self):
        """Integration metadata remains inside the authenticated application."""

        response = self.client.get("/integrations/")

        self.assertEqual(response.status_code, 401)

    @override_settings(
        JIRA_URL="https://jira.internal.example",
        TEAMCENTER_BASE_URL="https://teamcenter.internal.example",
        TEAMCENTER_USERNAME="service-user",
        TEAMCENTER_PASSWORD="service-password",
        DOCPROOF_URL="https://docproof.internal.example",
        AW_USERNAME="encoded-user",
        AW_PASSWORD="encoded-password",
    )
    def test_catalog_reports_capabilities_without_secrets(self):
        """Response contains readiness but never credentials or internal URLs."""

        self.client.force_authenticate(self.user)
        response = self.client.get("/integrations/")
        serialized = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["integrations"]), 7)
        self.assertNotIn("service-password", serialized)
        self.assertNotIn("internal.example", serialized)

    def test_catalog_contract_uses_unique_identifiers(self):
        """Frontend cards receive stable identifiers and capability lists."""

        self.client.force_authenticate(self.user)
        integrations = self.client.get("/integrations/").json()["integrations"]
        identifiers = [item["id"] for item in integrations]
        local_ai = next(item for item in integrations if item["id"] == "ai")

        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertTrue(all(isinstance(item["capabilities"], list) for item in integrations))
        self.assertIn("document-analysis", local_ai["capabilities"])

    @patch("awcenter.views.claim_refresh_slot", return_value=True)
    @patch("awcenter.views.probe_catalog")
    def test_live_probe_is_explicit_and_supports_refresh(
        self, probe_catalog_mock, claim_refresh_slot_mock
    ):
        """The API runs live checks only when an authenticated user requests them."""

        probe_catalog_mock.side_effect = lambda catalog, refresh: catalog
        self.client.force_authenticate(self.user)

        self.client.get("/integrations/")
        probe_catalog_mock.assert_not_called()

        response = self.client.get("/integrations/?probe=true&refresh=true")

        self.assertEqual(response.status_code, 200)
        probe_catalog_mock.assert_called_once()
        self.assertTrue(probe_catalog_mock.call_args.kwargs["refresh"])
        claim_refresh_slot_mock.assert_called_once_with(self.user.pk)
