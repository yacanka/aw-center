"""Tests for the project-specific DCC subtask control boundary."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from dcc.services.subtask_controls import (
    PROJECT_SUBTASK_CONTROLS,
    SubtaskControlResult,
    apply_project_subtask_control,
)


class ProjectSubtaskControlTests(SimpleTestCase):
    """Keep default rendering stable while allowing project algorithms."""

    def test_unregistered_project_preserves_subtasks_and_empty_context(self):
        """Projects without an algorithm retain the existing DCC behavior."""

        subtasks = [SimpleNamespace(key="ONE"), SimpleNamespace(key="TWO")]

        result = apply_project_subtask_control("ozgur", subtasks)

        self.assertEqual(result.subtasks, tuple(subtasks))
        self.assertEqual(result.render_context, {})
        self.assertEqual(result.placeholder_overrides, {})

    def test_registered_project_can_merge_ignore_and_add_render_context(self):
        """A handler may reshape panels and expose separately rendered data."""

        apple = SimpleNamespace(key="APPLE")
        pear = SimpleNamespace(key="PEAR")
        ignored = SimpleNamespace(key="IGNORE")

        def combine_fruit(subtasks):
            return SubtaskControlResult(
                subtasks=(subtasks[0],),
                render_context={"combined_name": f"{subtasks[0].key} + {subtasks[1].key}"},
            )

        controls = {**PROJECT_SUBTASK_CONTROLS, "abc": combine_fruit}
        with patch("dcc.services.subtask_controls.PROJECT_SUBTASK_CONTROLS", controls):
            result = apply_project_subtask_control("abc", [apple, pear, ignored])

        self.assertEqual(result.subtasks, (apple,))
        self.assertEqual(result.render_context, {"combined_name": "APPLE + PEAR"})

    def test_gokbey_handler_is_registered(self):
        """The production Gokbey rule is reached through the shared boundary."""

        panel = SimpleNamespace(
            fields=SimpleNamespace(
                summary="Flight Panel Assessment",
                assignee=SimpleNamespace(displayName="Ada Lovelace"),
            )
        )

        result = apply_project_subtask_control("gokbey", [panel])

        self.assertEqual(
            result.placeholder_overrides["Panel_AS_Name_1"],
            "Utku İnanç PEHLİVAN, Ada LOVELACE",
        )

    def test_malformed_project_result_is_rejected(self):
        """Invalid handlers fail explicitly instead of corrupting a DCC form."""

        controls = {**PROJECT_SUBTASK_CONTROLS, "abc": lambda _subtasks: {}}
        with patch("dcc.services.subtask_controls.PROJECT_SUBTASK_CONTROLS", controls):
            with self.assertRaisesRegex(TypeError, "SubtaskControlResult"):
                apply_project_subtask_control("abc", [])
