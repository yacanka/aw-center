"""DCC JIRA snapshot project-resolution tests."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from dcc.document_snapshot import DccSnapshotError, capture_dcc_snapshot
from dcc.service.text_parsing import extract_text_from_text


class DccDocumentSnapshotTests(SimpleTestCase):
    def test_multiple_resolved_projects_are_rejected_as_ambiguous(self):
        connector = Mock()
        connector.current_user.return_value = {"name": "jira-user"}
        connector.get_issue.return_value = SimpleNamespace(fields=SimpleNamespace(components=[]))
        definitions = (SimpleNamespace(slug="ozgur"), SimpleNamespace(slug="hys"))

        with (
            patch("dcc.document_snapshot.validate_parent_issue"),
            patch(
                "dcc.document_snapshot.resolve_projects_from_jira_components",
                return_value=definitions,
            ),
            self.assertRaises(DccSnapshotError) as raised,
        ):
            capture_dcc_snapshot(connector, "CHN-42", SimpleNamespace())

        self.assertEqual(raised.exception.code, "DCC_PROJECT_AMBIGUOUS")

    def test_missing_legacy_comment_markers_do_not_create_partial_values(self):
        self.assertEqual(extract_text_from_text("unstructured", "Start: ", " End"), "")
        self.assertEqual(extract_text_from_text("unstructured", "", " End"), "")
        self.assertEqual(extract_text_from_text("unstructured", "Start: ", ""), "")
