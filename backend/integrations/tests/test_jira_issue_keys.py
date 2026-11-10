"""Issue identity must survive the adapter boundary unchanged."""
from django.test import SimpleTestCase
from integrations.jira.client import JiraConnector


class JiraIssueKeyTests(SimpleTestCase):
    def test_valid_project_keys_are_not_rejected_or_truncated(self):
        connector = JiraConnector.__new__(JiraConnector)
        for key in ("CHN-42", "A2-42", "AB_CD-42"):
            for reference in (key, f"https://jira.example.test/browse/{key}"):
                with self.subTest(reference=reference):
                    connector.set_issue(reference)
                    self.assertEqual(connector.get_issue_key(), key)
