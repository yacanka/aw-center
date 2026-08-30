"""Tests for explicit project policy handlers."""

from django.test import SimpleTestCase

from projects.policies.gokbey import control_gokbey_dcc


class GokbeyDccPolicyTests(SimpleTestCase):
    def test_existing_mandatory_responsible_is_not_duplicated(self):
        result = control_gokbey_dcc(
            {
                "Panels": [
                    {
                        "Panel_Name": "Flight Panel Assessment",
                        "Panel_AS_Name": "Utku İnanç PEHLİVAN",
                    }
                ]
            }
        )
        self.assertEqual(
            result["Panels"][0]["Panel_AS_Name"],
            "Utku İnanç PEHLİVAN",
        )

    def test_render_controller_merges_mandatory_and_jira_responsibles(self):
        result = control_gokbey_dcc(
            {
                "Panels": [
                    {
                        "Panel_Name": "Flight Panel Assessment",
                        "Panel_AS_Name": "Ada LOVELACE",
                    }
                ]
            }
        )

        self.assertEqual(
            result["Panels"][0]["Panel_AS_Name"],
            "Utku İnanç PEHLİVAN, Ada LOVELACE",
        )

    def test_unknown_panel_is_preserved(self):
        source = {
            "Panels": [
                {
                    "Panel_Name": "Safety Panel Assessment",
                    "Panel_AS_Name": "Ada LOVELACE",
                }
            ]
        }

        result = control_gokbey_dcc(source)

        self.assertEqual(result, source)
