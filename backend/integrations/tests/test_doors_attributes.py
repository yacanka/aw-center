"""Attribute-only DOORS reads never export object values or partial lists."""

from unittest.mock import Mock

from django.test import SimpleTestCase

from integrations.doors import builder_read
from integrations.doors.client import DoorsClient
from integrations.doors.config import DoorsClientConfig
from integrations.doors.exceptions import DoorsDxlError, DoorsOperationError
from integrations.doors.transport import DxlExecution


class DoorsAttributeReadTests(SimpleTestCase):
    """Validate the attribute-only protocol at the DOORS client boundary."""

    def read_client(self, lines):
        """Use controlled transport output without a Windows DOORS installation."""
        transport = Mock()
        transport.run_dxl.return_value = DxlExecution("result", tuple(lines))
        return DoorsClient(DoorsClientConfig("doors.exe"), transport=transport)

    def test_builder_reads_bounded_attribute_names_without_objects(self):
        script = builder_read.list_attributes('/Project/Module"')
        self.assertIn(r'"/Project/Module\""', script)
        self.assertIn("if (!awc_attribute.object) continue", script)
        self.assertIn("awc_count >= 1000", script)
        self.assertNotIn('"OBJECT\\t"', script)
        self.assertNotIn("save(", script)

    def test_client_decodes_names_and_accepts_empty_modules(self):
        client = self.read_client([
            "ATTRIBUTE\tObject Text", "ATTRIBUTE\tLine\\nName", "OK\tLIST_ATTRIBUTES_DONE",
        ])
        self.assertEqual(client.list_attributes("/P/M"), ["Line\nName", "Object Text"])
        self.assertEqual(
            self.read_client(["OK\tLIST_ATTRIBUTES_DONE"]).list_attributes("/P/M"), []
        )

    def test_discovery_includes_builtins_without_duplicate_protocol_records(self):
        script = builder_read.list_attributes("/P/M")
        for name in ("Object Heading", "Object Number", "Absolute Number"):
            self.assertIn(f'awc_emit("ATTRIBUTE\\t{name}")', script)
            self.assertIn(f'awc_attribute.name == "{name}"', script)
        self.assertIn("int awc_count = 3", script)

    def test_client_rejects_truncated_partial_or_malformed_lists(self):
        for lines in (
            ["ATTRIBUTE\tName"],
            ["ATTRIBUTES_TRUNCATED", "OK\tLIST_ATTRIBUTES_DONE"],
            ["ATTRIBUTE\t", "OK\tLIST_ATTRIBUTES_DONE"],
            ["ATTRIBUTE\tName\textra", "OK\tLIST_ATTRIBUTES_DONE"],
            ["OBJECT\tsecret", "OK\tLIST_ATTRIBUTES_DONE"],
            ["ATTRIBUTE\tName", "ATTRIBUTE\tName", "OK\tLIST_ATTRIBUTES_DONE"],
        ):
            with self.subTest(lines=lines), self.assertRaises(DoorsDxlError):
                self.read_client(lines).list_attributes("/P/M")

    def test_client_rejects_over_limit_and_open_errors(self):
        with self.assertRaises(DoorsDxlError):
            self.read_client(
                [f"ATTRIBUTE\tName{i}" for i in range(1001)] + ["OK\tLIST_ATTRIBUTES_DONE"]
            ).list_attributes("/P/M")
        with self.assertRaises(DoorsOperationError):
            self.read_client(["ERR\tOPEN_MODULE\tAccess denied"]).list_attributes("/P/M")
