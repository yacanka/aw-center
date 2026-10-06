"""Watcher completion and reminder recipient selection share Jira semantics."""
from types import SimpleNamespace as NS
from unittest.mock import Mock
from django.test import SimpleTestCase
from integrations.jira.client import JiraConnector


class JiraOpenSubtaskTests(SimpleTestCase):
    def test_done_category_and_terminal_fallbacks_do_not_receive_reminders(self):
        connector = JiraConnector.__new__(JiraConnector)
        connector.issue_key = "CHN-1"
        tasks = {
            "CHN-2": NS(fields=NS(status=NS(name="In Review", statusCategory=NS(key="indeterminate")))),
            "CHN-3": NS(fields=NS(status=NS(name="Accepted", statusCategory=NS(key="done")))),
            "CHN-4": NS(fields=NS(status=NS(name="Done"))),
            "CHN-5": NS(fields=NS(status=NS(name="Closed"))),
        }
        parent = NS(fields=NS(subtasks=[NS(key=key) for key in tasks]))
        connector.jira = Mock()
        connector.jira.issue.side_effect = lambda key: parent if key == "CHN-1" else tasks[key]
        self.assertEqual(connector.get_open_subtask(), [tasks["CHN-2"]])
