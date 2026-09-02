"""Tests for DB-independent DOORS runner task adapters."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from integrations.doors.runner_tasks import (
    RunnerTaskPayloadError,
    create_object,
    execute_dxl,
    link_requirements,
    update_object,
)


class DoorsRunnerTaskTests(SimpleTestCase):
    """Verify artifact-only payloads delegate to allowlisted client methods."""

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_execute_dxl_dispatches_only_named_read_operation(self, execute):
        client = Mock()
        client.check_module.return_value.ok = True
        execute.side_effect = lambda operation: operation(client)

        result, output = self.run_task(
            execute_dxl,
            {"operation": "check_module", "module_path": "/Project/Module"},
        )

        self.assertTrue(json.loads(output.read_text())["accessible"])
        self.assertEqual(result["filename"], "doors-result.json")
        client.check_module.assert_called_once_with("/Project/Module")

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_execute_dxl_lists_objects_with_validated_bounds(self, execute):
        """List artifacts delegate all validated bounds to the Windows client."""

        client = Mock()
        item = Mock()
        item.to_dict.return_value = {"absolute_number": 42}
        client.list_objects.return_value = [item]
        execute.side_effect = lambda operation: operation(client)

        _result, output = self.run_task(
            execute_dxl,
            {
                "operation": "list_objects",
                "module_path": "/Project/Module",
                "attributes": ["Object Text"],
                "loop": "entire",
                "limit": 25,
            },
        )

        client.list_objects.assert_called_once_with(
            "/Project/Module", ["Object Text"], "entire", 25
        )
        self.assertEqual(json.loads(output.read_text())["count"], 1)

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_execute_dxl_exports_module_for_compliance_import(self, execute):
        client = Mock()
        client.export_module.return_value = {
            "columns": ["Document Name", "Cover Number"],
            "results": [{"attributes": {"Document Name": "Doc", "Cover Number": "CP"}}],
            "truncated": False,
            "attributes_truncated": False,
        }
        execute.side_effect = lambda operation: operation(client)

        _result, output = self.run_task(
            execute_dxl,
            {
                "operation": "export_module",
                "module_path": "/Project/Module",
                "limit": 10000,
            },
        )

        payload = json.loads(output.read_text())
        client.export_module.assert_called_once_with("/Project/Module", 10000)
        self.assertEqual(payload["type"], "doors_module_export")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["columns"], ["Document Name", "Cover Number"])
        self.assertFalse(payload["truncated"])
        self.assertFalse(payload["attributes_truncated"])

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_execute_dxl_reads_one_object(self, execute):
        """Object-detail artifacts cannot select an arbitrary client method."""

        client = Mock()
        item = Mock()
        item.to_dict.return_value = {"absolute_number": 42}
        client.get_object.return_value = item
        execute.side_effect = lambda operation: operation(client)

        self.run_task(
            execute_dxl,
            {
                "operation": "get_object",
                "module_path": "/Project/Module",
                "absolute_number": 42,
                "attributes": ["Object Text"],
            },
        )

        client.get_object.assert_called_once_with(
            "/Project/Module", 42, ["Object Text"]
        )

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_execute_dxl_checks_disciplines(self, execute):
        """Discipline checks dispatch only the fixed high-level client operation."""

        client = Mock()
        item = Mock()
        item.to_dict.return_value = {"absolute_number": 42}
        client.check_applicable_disciplines.return_value = [item]
        execute.side_effect = lambda operation: operation(client)

        _result, output = self.run_task(
            execute_dxl,
            {
                "operation": "check_applicable_disciplines",
                "module_path": "/Project/Module",
            },
        )

        client.check_applicable_disciplines.assert_called_once_with("/Project/Module")
        self.assertEqual(json.loads(output.read_text())["count"], 1)

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_execute_dxl_rejects_arbitrary_operation(self, execute):
        with self.assertRaises(RunnerTaskPayloadError):
            self.run_task(execute_dxl, {"operation": "raw_dxl", "script": "delete all"})
        execute.assert_not_called()

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_execute_dxl_rejects_unknown_or_credential_fields(self, execute):
        """Artifacts cannot smuggle credentials past an operation serializer."""

        with self.assertRaisesRegex(
            RunnerTaskPayloadError,
            "DOORS automation payload failed validation.",
        ):
            self.run_task(
                execute_dxl,
                {
                    "operation": "check_module",
                    "module_path": "/Project/Module",
                    "password": "must-not-cross-the-runner",
                },
            )
        execute.assert_not_called()

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_malformed_payload_returns_sanitized_error(self, execute):
        """Parser details and invalid content never escape the task boundary."""

        with self.assertRaisesRegex(
            RunnerTaskPayloadError,
            "^DOORS automation payload is invalid\\.$",
        ) as raised:
            self.run_raw_task(execute_dxl, b'{"sensitive-value"')
        self.assertNotIn("sensitive-value", str(raised.exception))
        execute.assert_not_called()

    @override_settings(DOORS_RUNNER_MAX_INPUT_BYTES=16)
    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_payload_limit_matches_runner_catalog_policy(self, execute):
        """Oversized artifacts fail before client construction on the runner."""

        with self.assertRaisesRegex(
            RunnerTaskPayloadError,
            "DOORS automation payload size is invalid.",
        ):
            self.run_task(
                execute_dxl,
                {"operation": "check_module", "module_path": "/Project/Module"},
            )
        execute.assert_not_called()

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_update_object_uses_validated_scalar_contract(self, execute):
        client = Mock()
        execute.side_effect = lambda operation: operation(client)

        _result, output = self.run_task(
            update_object,
            {
                "module_path": "/Project/Module",
                "absolute_number": 42,
                "attributes": {"Object Text": "Reviewed"},
            },
        )

        client.set_object_attributes.assert_called_once_with(
            "/Project/Module", 42, {"Object Text": "Reviewed"}
        )
        self.assertTrue(json.loads(output.read_text())["updated"])

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_update_object_rejects_nested_values(self, execute):
        """Unsupported nested values fail before any Windows-side call."""

        with self.assertRaisesRegex(
            RunnerTaskPayloadError,
            "DOORS automation payload failed validation.",
        ):
            self.run_task(
                update_object,
                {
                    "module_path": "/Project/Module",
                    "absolute_number": 42,
                    "attributes": {"Object Text": {"nested": True}},
                },
            )
        execute.assert_not_called()

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_create_object_writes_bounded_representation(self, execute):
        client = Mock()
        created = Mock()
        created.to_dict.return_value = {
            "absolute_number": 43,
            "identifier": "REQ-43",
            "level": 1,
            "attributes": {"Object Text": "Created"},
        }
        client.create_object.return_value = created
        execute.side_effect = lambda operation: operation(client)

        _result, output = self.run_task(
            create_object,
            {
                "module_path": "/Project/Module",
                "position": "after",
                "relative_absolute_number": 42,
                "attributes": {"Object Text": "Created"},
            },
        )

        client.create_object.assert_called_once_with(
            "/Project/Module", "after", 42, {"Object Text": "Created"}
        )
        self.assertEqual(json.loads(output.read_text())["absolute_number"], 43)

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_link_requirements_uses_only_the_validated_client_operation(self, execute):
        """The agent receives structured Linker fields rather than executable DXL."""

        client = Mock()
        client.link_requirements.return_value = {
            "type": "doors_requirement_linker",
            "schema_version": 1,
            "mode": "preview",
            "groups": [],
        }
        execute.side_effect = lambda operation: operation(client)
        payload = {
            "ref_module_name": "/Project/Reference",
            "target_module_name": "/Project/Target",
            "link_module_name": "/Project/Links",
            "ref_attr_poc": "PoC List",
            "ref_attr_req": "Requirement",
            "target_attr_poc": "PoC Info",
            "start_index": 0,
            "text_length": -1,
            "direction": "ref2tar",
            "activeness": False,
        }

        _result, output = self.run_task(link_requirements, payload)

        client.link_requirements.assert_called_once_with(payload)
        self.assertEqual(json.loads(output.read_text())["mode"], "preview")

    @patch("integrations.doors.runner_tasks.execute_with_client")
    def test_link_requirements_rejects_script_or_unknown_fields(self, execute):
        """A runner artifact cannot append arbitrary code to the Linker contract."""

        with self.assertRaisesRegex(
            RunnerTaskPayloadError,
            "DOORS automation payload failed validation.",
        ):
            self.run_task(
                link_requirements,
                {
                    "ref_module_name": "/Project/Reference",
                    "target_module_name": "/Project/Target",
                    "link_module_name": "/Project/Links",
                    "ref_attr_poc": "PoC List",
                    "ref_attr_req": "Requirement",
                    "target_attr_poc": "PoC Info",
                    "start_index": 0,
                    "text_length": -1,
                    "direction": "ref2tar",
                    "activeness": True,
                    "script": "delete all",
                },
            )
        execute.assert_not_called()

    def run_task(self, task, payload):
        return self.run_raw_task(task, json.dumps(payload).encode("utf-8"))

    def run_raw_task(self, task, payload):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            input_path = directory / "input.json"
            output_path = directory / "output.json"
            input_path.write_bytes(payload)
            result = task(input_path, output_path)
            copied_output = directory / "copied.json"
            copied_output.write_bytes(output_path.read_bytes())
            return result, DetachedPath(copied_output.read_bytes())


class DetachedPath:
    """Retain temporary output bytes after the task directory is removed."""

    def __init__(self, content):
        self.content = content

    def read_text(self):
        return self.content.decode("utf-8")
