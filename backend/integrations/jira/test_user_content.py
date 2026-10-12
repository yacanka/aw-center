"""Saved JIRA lists are bounded, private and protected against stale writes."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


URL = "/api/integrations/jira/subtasks/saved-lists/"


class JiraUserContentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("saved-lists-owner")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_lists_round_trip_without_preferences_and_reject_stale_writes(self):
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(self.client.get(URL).data, {"lists": [], "version": 0})
        lists = [{"title": "Draft", "fields": [], "list": [{"summary": "", "fields": {"customfield_123": None}}]}]
        response = self.client.put(URL, {"lists": lists, "version": 0}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {"lists": lists, "version": 1})
        stale = self.client.put(URL, {"lists": [], "version": 0}, format="json")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "JIRA_CONTENT_VERSION_CONFLICT")
        self.assertEqual(self.client.get(URL).data, {"lists": lists, "version": 1})
        self.client.post("/api/users/preferences/reset/")
        self.assertEqual(self.client.get(URL).data, {"lists": lists, "version": 1})

    def test_lists_are_owner_scoped(self):
        self.client.put(URL, {"lists": [{"title": "Private", "list": []}], "version": 0}, format="json")
        self.client.force_authenticate(get_user_model().objects.create_user("another-owner"))
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(self.client.get(URL).data, {"lists": [], "version": 0})

    def test_invalid_shapes_and_limits_are_rejected(self):
        payloads = [{"lists": {}}, {"lists": [1]}, {"lists": [{"title": "Draft", "list": {}}]},
                    {"lists": [{"title": "Draft", "list": [], "fields": {}}]},
                    {"lists": [{"title": "Draft", "list": []}] * 51},
                    {"lists": [{"title": "Draft", "list": [{}] * 101}]},
                    {"lists": [{"title": "Draft", "fields": [{}] * 101, "list": []}]},
                    {"lists": [{"title": "ü" * (1024 * 1024), "list": []}]},
                    {"lists": [], "owner": self.user.pk}, {"lists": [], "version": True}]
        for payload in payloads:
            with self.subTest(payload_keys=list(payload)):
                response = self.client.put(URL, {"version": 0, **payload}, format="json")
                self.assertEqual(response.status_code, 400)

    def test_unsafe_requests_require_csrf_and_anonymous_reads_fail(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertIn(client.get(URL).status_code, (401, 403))
        client.force_login(self.user)
        self.assertEqual(client.put(URL, {"lists": [], "version": 0}, format="json").status_code, 403)
