"""Tests for Gokbey Jandarma DCC subtask rules."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from projects.gokbey.dcc_subtasks import control_jandarma_subtasks


def panel(summary, assignee):
    """Build the bounded JIRA field shape used by the project rule."""

    return SimpleNamespace(
        fields=SimpleNamespace(
            summary=summary,
            assignee=SimpleNamespace(displayName=assignee) if assignee else None,
        )
    )


class GokbeyJandarmaSubtaskTests(SimpleTestCase):
    """Verify the historical mandatory-responsible panel behavior."""

    def test_mandatory_responsibles_are_merged_with_jira_assignees(self):
        """Known panels retain assignees and prepend mandatory responsibles."""

        result = control_jandarma_subtasks(
            (
                panel("Flight Panel Assessment", "Ada Lovelace"),
                panel("Human Factor Panel Assessment", "Grace Hopper"),
                panel("Electrical Systems/E3 Panel Assessment", "Alan Turing"),
            )
        )

        self.assertEqual(
            result.placeholder_overrides,
            {
                "Panel_AS_Name_1": "Utku İnanç PEHLİVAN, Ada LOVELACE",
                "Panel_AS_Name_2": "Aslı ALPSOY, Grace HOPPER",
                "Panel_AS_Name_3": "Merve HELVACI, Alan TURING",
            },
        )
        self.assertEqual(len(result.render_context["mandatory_panel_responsibles"]), 3)

    def test_unknown_panel_is_preserved_without_override(self):
        """Unconfigured panels continue through the standard renderer unchanged."""

        source = panel("Safety Panel Assessment", "Ada Lovelace")

        result = control_jandarma_subtasks((source,))

        self.assertEqual(result.subtasks, (source,))
        self.assertEqual(result.placeholder_overrides, {})

    def test_existing_mandatory_responsible_is_not_duplicated(self):
        """Matching JIRA assignments remain a single display value."""

        result = control_jandarma_subtasks(
            (panel("Flight Panel Assessment", "Utku İnanç Pehlivan"),)
        )

        self.assertEqual(result.placeholder_overrides["Panel_AS_Name_1"], "Utku İnanç PEHLİVAN")
