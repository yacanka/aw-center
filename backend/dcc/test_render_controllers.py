"""Tests for the project-specific pre-render DCC controller boundary."""

from unittest.mock import patch

from django.test import SimpleTestCase

from dcc.services.render_controllers import apply_project_dcc_controller
from projects.types import ProjectDefinition


class ProjectDccRenderControllerTests(SimpleTestCase):
    def test_project_without_controller_receives_an_isolated_context(self):
        source = {"Panels": [{"Panel_AS_Name": "Ada LOVELACE"}]}

        result = apply_project_dcc_controller("hys", source)
        result["Panels"][0]["Panel_AS_Name"] = "Changed"

        self.assertEqual(source["Panels"][0]["Panel_AS_Name"], "Ada LOVELACE")

    def test_registered_controller_can_manipulate_data_before_render(self):
        definition = ProjectDefinition(slug="example", dcc_controller="example_dcc")

        def control(context):
            context["Controlled_Value"] = context["Source_Value"].upper()
            return context

        with (
            patch(
                "dcc.services.render_controllers.get_project_definition",
                return_value=definition,
            ),
            patch(
                "dcc.services.render_controllers.CONTROLLERS",
                {"example_dcc": control},
            ),
        ):
            result = apply_project_dcc_controller("example", {"Source_Value": "ready"})

        self.assertEqual(result["Controlled_Value"], "READY")

    def test_controller_can_filter_and_merge_panel_array_items(self):
        definition = ProjectDefinition(slug="example", dcc_controller="example_dcc")
        source = {
            "Panels": [
                {"Panel_Name": "Flight", "Panel_AS_Name": "Ada"},
                {"Panel_Name": "Flight", "Panel_AS_Name": "Grace"},
                {"Panel_Name": "Ignored", "Panel_AS_Name": "Alan"},
            ]
        }

        def control(context):
            first, second, _ignored = context["Panels"]
            first["Panel_AS_Name"] = f'{first["Panel_AS_Name"]}, {second["Panel_AS_Name"]}'
            context["Panels"] = [first]
            return context

        with (
            patch(
                "dcc.services.render_controllers.get_project_definition",
                return_value=definition,
            ),
            patch(
                "dcc.services.render_controllers.CONTROLLERS",
                {"example_dcc": control},
            ),
        ):
            result = apply_project_dcc_controller("example", source)

        self.assertEqual(
            result["Panels"],
            [{"Panel_Name": "Flight", "Panel_AS_Name": "Ada, Grace"}],
        )
        self.assertEqual(len(source["Panels"]), 3)

    def test_malformed_controller_result_is_rejected(self):
        definition = ProjectDefinition(slug="example", dcc_controller="example_dcc")
        with (
            patch(
                "dcc.services.render_controllers.get_project_definition",
                return_value=definition,
            ),
            patch(
                "dcc.services.render_controllers.CONTROLLERS",
                {"example_dcc": lambda _context: []},
            ),
            self.assertRaisesRegex(TypeError, "must return a mapping"),
        ):
            apply_project_dcc_controller("example", {})

    def test_controller_cannot_replace_panel_array_with_an_invalid_value(self):
        definition = ProjectDefinition(slug="example", dcc_controller="example_dcc")
        with (
            patch(
                "dcc.services.render_controllers.get_project_definition",
                return_value=definition,
            ),
            patch(
                "dcc.services.render_controllers.CONTROLLERS",
                {"example_dcc": lambda _context: {"Panels": "invalid"}},
            ),
            self.assertRaisesRegex(TypeError, "preserve Panels as a list"),
        ):
            apply_project_dcc_controller("example", {})
