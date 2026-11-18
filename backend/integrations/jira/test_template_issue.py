from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from jira import JIRAError
from rest_framework.exceptions import APIException

from .template_issue import read_template_issue, template_issue_key


@override_settings(JIRA_URL="https://jira.example.test/context")
class TemplateIssueTests(SimpleTestCase):
    def test_only_keys_and_configured_browse_urls_are_accepted(self):
        self.assertEqual(template_issue_key(" i-14 "), "I-14")
        self.assertEqual(template_issue_key("https://JIRA.example.test:443/context/browse/i-14"), "I-14")
        for ref in ("https://other.test/context/browse/I-14", "https://jira.example.test/browse/I-14",
                    "https://user@jira.example.test/context/browse/I-14",
                    "https://jira.example.test/context/browse/I-14/extra", "I-14 OR I-42", {}):
            with self.subTest(ref=ref), self.assertRaises(APIException):
                template_issue_key(ref)

    @patch("integrations.jira.template_issue.jira_connector_for")
    def test_source_uses_owner_session_with_visible_field_ids_and_no_project_roles(self, factory):
        actor = object()
        factory.return_value.get_client.return_value.issue.return_value = SimpleNamespace(raw={
            "key": "NEW-1",
            "names": {"customfield_1": "Repeated", "customfield_2": "Repeated", "hidden": "Secret"},
            "schema": {"customfield_1": {"type": "date"}, "created": {"type": "datetime"},
                       "customfield_2": {"type": "option-with-child"}},
            "fields": {"project": {"id": "101", "name": "External"},
                       "issuetype": {"id": "102", "name": "Sub-task", "subtask": True},
                       "customfield_1": "2026-10-10", "created": "2026-10-10T23:15:00.000+0000",
                       "customfield_2": {"value": "Parent", "child": {"value": "Child"}},
                       "long": "s" * 3000, "labels": ["x", "y"], "count": 0, "checked": False, "attachment": [], "issuelinks": [],
                       "assignee": {"displayName": "Operator", "emailAddress": "internal"},
                       "unknown": {"nested": {"key": "private"}}, "empty": None},
        })
        result = read_template_issue(actor, "OLD-1")
        factory.assert_called_once_with(actor)
        factory.return_value.get_client.return_value.issue.assert_called_once_with(
            "OLD-1", fields="*all", expand="names,schema")
        self.assertEqual(result["issue"], "NEW-1")
        self.assertEqual((result["project_id"], result["issue_type_id"]), ("101", "102"))
        fields = {row["id"]: row for row in result["fields"]}
        self.assertNotIn("hidden", fields)
        self.assertEqual(fields["customfield_1"]["name"], fields["customfield_2"]["name"])
        self.assertEqual(fields["customfield_1"]["value"], "10.10.2026")
        self.assertEqual(fields["created"]["value"], "11.10.2026 02:15")
        self.assertEqual(fields["customfield_2"]["value"], "Parent / Child")
        for key, value in {"key": "NEW-1", "long": "s" * 3000, "labels": "x\ny", "count": "0",
                           "checked": "false", "empty": "", "assignee": "Operator"}.items():
            self.assertTrue(fields[key]["supported"])
            self.assertEqual(fields[key]["value"], value)
        for identifier in ("unknown", "attachment", "issuelinks"):
            self.assertFalse(fields[identifier]["supported"])
        self.assertNotIn("private", str(result))
        self.assertNotIn("internal", str(result))

    @patch("integrations.jira.template_issue.jira_connector_for")
    def test_rich_text_preserves_lines_and_complex_or_oversized_values_are_flagged(self, factory):
        paragraph = {"type": "paragraph", "content": [{"type": "text", "text": "a"},
                     {"type": "hardBreak"}, {"type": "text", "text": "b"}]}
        factory.return_value.get_client.return_value.issue.return_value = SimpleNamespace(raw={
            "key": "EX-1", "fields": {
                "project": {"id": "10", "name": "Example"}, "issuetype": {"id": "2", "name": "Custom"},
                "description": {"type": "doc", "content": [paragraph, paragraph]},
                "embedded": {"type": "doc", "content": [paragraph, {"type": "media"}]},
                "large": "x" * 32_769, "partially_displayable": ["displayable", {"nested": 1}],
                "malformedDate": "bad", "badXmlText": "a\x00b",
            },
            "schema": {"malformedDate": {"type": "date"}},
        })
        fields = {item["id"]: item for item in read_template_issue(object(), "EX-1")["fields"]}
        self.assertEqual(fields["description"]["value"], "a\nb\na\nb")
        for key in ("embedded", "large", "partially_displayable", "malformedDate", "badXmlText"):
            self.assertFalse(fields[key]["supported"])
            self.assertEqual(fields[key]["value"], "")

    @patch("integrations.jira.template_issue.jira_connector_for")
    def test_provider_error_is_sanitized_and_permissions_preserved(self, factory):
        for code, expected in ((401, 409), (403, 403), (404, 404), (500, 502)):
            factory.return_value.get_client.return_value.issue.side_effect = JIRAError(text="private", status_code=code)
            with self.subTest(code=code), self.assertRaises(APIException) as caught:
                read_template_issue(object(), "KEY-1")
            self.assertEqual(caught.exception.status_code, expected)
            self.assertNotIn("private", str(caught.exception))
