from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .client.builder_read import list_objects
from .client.config import DoorsClientConfig
from .client.escape import decode_field, dxl_quote
from .client.exceptions import DoorsConnectionError
from .client.transport import DoorsOleTransport
from .serializers import ObjectCreateSerializer, ObjectUpdateSerializer
from .services import initialized_com


class DoorsClientFoundationTests(SimpleTestCase):
    """Verify safe DXL construction and line decoding."""

    def test_dxl_quote_escapes_code_breakout_characters(self):
        """Quotes, slashes, and newlines remain inside one DXL literal."""
        quoted = dxl_quote('Module"\nunsafe')

        self.assertEqual(quoted, '"Module\\"\\nunsafe"')

    def test_decode_field_restores_line_protocol_characters(self):
        """Escaped result fields round-trip tabs, newlines, and slashes."""
        decoded = decode_field(r"first\tsecond\nthird\\tail")

        self.assertEqual(decoded, "first\tsecond\nthird\\tail")

    def test_list_builder_applies_server_side_result_limit(self):
        """Generated DXL stops iterating at the validated result limit."""
        script = list_objects("/Project/Module", ["Object Text"], "entire", 25)

        self.assertIn("if (__aw_count >= 25) break", script)
        self.assertIn('read("/Project/Module", false)', script)

    def test_start_command_uses_argument_list_for_database(self):
        """Optional database selection never passes through a shell string."""
        config = DoorsClientConfig(r"C:\IBM\DOORS\doors.exe", database="36677@doors.example")

        command = DoorsOleTransport(config).start_command()

        self.assertEqual(command, [r"C:\IBM\DOORS\doors.exe", "-d", "36677@doors.example"])

    def test_running_client_uses_dispatch_when_rot_lookup_fails(self):
        """A running DOORS process is reused even when ROT lookup misses it."""
        transport = DoorsOleTransport(DoorsClientConfig(r"C:\IBM\DOORS\doors.exe"))
        automation = Mock()
        automation.GetActiveObject.side_effect = RuntimeError("not registered")
        automation.Dispatch.return_value = Mock()

        with patch.object(transport, "is_client_running", return_value=True):
            application = transport.get_active_application(automation)

        self.assertIs(application, automation.Dispatch.return_value)
        automation.Dispatch.assert_called_once_with("DOORS.Application")

    def test_process_inspection_matches_configured_executable_name(self):
        """Process inspection identifies the configured DOORS executable."""
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe"))
        inspector = Mock()
        inspector.return_value.Win32_Process.return_value = [Mock(Name="DOORS.EXE")]

        with patch.object(transport, "load_process_inspector", return_value=inspector):
            is_running = transport.is_client_running()

        self.assertTrue(is_running)

    def test_running_client_is_not_started_again_when_ole_is_not_ready(self):
        """An existing process blocks auto-start while its OLE object initializes."""
        transport = DoorsOleTransport(
            DoorsClientConfig(r"C:\IBM\DOORS\doors.exe", auto_start_client=True)
        )
        automation = Mock()
        with (
            patch.object(transport, "load_automation", return_value=automation),
            patch.object(transport, "get_active_application", return_value=None),
            patch.object(transport, "is_client_running", return_value=True),
            patch.object(
                transport,
                "wait_for_application",
                side_effect=DoorsConnectionError("not ready"),
            ),
            patch.object(transport, "start_client") as start_client,
        ):
            with self.assertRaises(DoorsConnectionError):
                transport.connect()
        start_client.assert_not_called()

    def test_absent_client_can_still_be_started_when_enabled(self):
        """Auto-start remains available when no DOORS process exists."""
        config = DoorsClientConfig(r"C:\IBM\DOORS\doors.exe", auto_start_client=True)
        transport = DoorsOleTransport(config)
        automation = Mock()

        with (
            patch.object(transport, "load_automation", return_value=automation),
            patch.object(transport, "get_active_application", return_value=None),
            patch.object(transport, "is_client_running", return_value=False),
            patch.object(transport, "start_client") as start_client,
        ):
            start_client.side_effect = lambda _: setattr(transport, "application", Mock())
            transport.connect()

        start_client.assert_called_once_with(automation)

    def test_update_serializer_rejects_nested_attribute_values(self):
        """Nested data cannot be stringified into unexpected DXL assignments."""
        serializer = ObjectUpdateSerializer(
            data={
                "module_path": "/Project/Module",
                "absolute_number": 1,
                "attributes": {"Object Text": {"nested": True}},
            }
        )

        self.assertFalse(serializer.is_valid())

    def test_create_serializer_requires_relative_object(self):
        """Relative insertion modes require an absolute object number."""
        serializer = ObjectCreateSerializer(
            data={
                "module_path": "/Project/Module",
                "position": "after",
                "attributes": {"Object Text": "New"},
            }
        )

        self.assertFalse(serializer.is_valid())

    @patch("doors.services.sys.platform", "linux")
    def test_com_initialization_fails_closed_outside_windows(self):
        """Non-Windows workers cannot attempt platform-specific OLE imports."""
        with self.assertRaises(DoorsConnectionError):
            with initialized_com():
                pass


@override_settings(
    DOORS_EXECUTABLE=r"C:\IBM\DOORS\doors.exe",
    DOORS_DATABASE="36677@doors.example",
    DOORS_OLE_PROG_ID="DOORS.Application",
    DOORS_PREFER_ACTIVE_INSTANCE=True,
    DOORS_AUTO_START_CLIENT=False,
    DOORS_STARTUP_TIMEOUT_SECONDS=30.0,
    DOORS_RUN_TIMEOUT_SECONDS=120.0,
)
class DoorsApiTests(TestCase):
    """Verify DOORS API authorization and adapter delegation."""

    def setUp(self):
        """Create an authenticated non-administrator API client."""
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="doors-user")
        self.client.force_authenticate(self.user)

    def test_status_never_returns_database_or_credentials(self):
        """DOORS readiness output contains no database or secret values."""
        response = self.client.get(reverse("doors_status"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("database", response.data)
        self.assertNotIn("password", response.data)

    @patch("doors.api_views.execute_with_client")
    def test_module_check_delegates_validated_path(self, execute_client):
        """A valid module path reaches the COM service boundary."""
        execute_client.return_value = {"accessible": True, "module_path": "/Project/Module"}

        response = self.client.post(
            reverse("doors_check_module"), {"module_path": "/Project/Module"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        operation = execute_client.call_args.args[0]
        fake_client = Mock()
        fake_client.check_module.return_value.ok = True
        self.assertTrue(operation(fake_client)["accessible"])
        fake_client.check_module.assert_called_once_with("/Project/Module")

    def test_object_update_requires_administrator(self):
        """A normal authenticated user cannot mutate DOORS objects."""
        response = self.client.patch(reverse("doors_update_object"), {}, format="json")

        self.assertEqual(response.status_code, 403)
