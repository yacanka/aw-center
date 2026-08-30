import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from jobs.models import Job

from integrations.doors.builder_read import list_objects
from integrations.doors.builder_link import link_requirements
from integrations.doors.client import DoorsClient
from integrations.doors.config import DoorsClientConfig
from integrations.doors.escape import decode_field, dxl_quote
from integrations.doors.exceptions import DoorsConnectionError
from integrations.doors.transport import DoorsOleTransport, DxlExecution
from integrations.doors.serializers import ObjectCreateSerializer, ObjectUpdateSerializer
from integrations.doors.services import initialized_com


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

        self.assertIn("if (awc_count >= 25) break", script)
        self.assertIn('read("/Project/Module", false)', script)

    def test_linker_builder_escapes_input_and_preserves_direction(self):
        """The fixed Linker emits no caller-controlled DXL and edits only its source."""

        script = link_requirements(
            'Reference"\nunsafe',
            "/Project/Target",
            "/Project/Links",
            "PoC List",
            "Requirement",
            "PoC Info",
            2,
            -1,
            "ref2tar",
            True,
        )

        self.assertIn('string awc_ref_module_name = "Reference\\"\\nunsafe"', script)
        self.assertIn("Module awc_ref_module = edit", script)
        self.assertIn("Module awc_target_module = read", script)
        self.assertIn("awc_link_source -> awc_link_module_name -> awc_link_target", script)
        self.assertIn("save(awc_ref_module)", script)
        self.assertIn("Skip awc_groups = createString", script)
        self.assertNotIn("yck.dxl", script)

    def test_linker_builder_reverses_source_without_changing_matching(self):
        """Target-to-reference mode edits and saves the target module only."""

        script = link_requirements(
            "/Project/Reference",
            "/Project/Target",
            "/Project/Links",
            "PoC List",
            "Requirement",
            "PoC Info",
            0,
            8,
            "tar2ref",
            True,
        )

        self.assertIn("Module awc_ref_module = read", script)
        self.assertIn("Module awc_target_module = edit", script)
        self.assertIn("Object awc_link_source = awc_matched_target", script)
        self.assertIn("Object awc_link_target = awc_group_object", script)
        self.assertIn("save(awc_target_module)", script)

    def test_linker_client_returns_grouped_preview_and_summary(self):
        """Line-oriented DXL output becomes the typed result consumed by the page."""

        transport = Mock()
        transport.run_dxl.return_value = DxlExecution(
            "AW_DOORS_OK|result",
            (
                "GROUP\tPoC-1\tREQ-1",
                "GROUP\tPoC-1\tREQ-2",
                "TARGET\tPoC-1",
                "GROUP\tPoC-2\tREQ-3",
                "MISSING\tPoC-2",
                "SUMMARY\t3\t2\t3\t1\t1\t0\t0",
                "OK\tREQUIREMENT_LINKER_DONE",
            ),
        )
        client = DoorsClient(DoorsClientConfig("doors.exe"), transport=transport)
        values = {
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

        result = client.link_requirements(values)

        self.assertEqual(result["summary"]["candidates"], 3)
        self.assertEqual(result["groups"][0]["requirements"], ["REQ-1", "REQ-2"])
        self.assertTrue(result["groups"][0]["target_found"])
        self.assertEqual(result["missing_targets"], ["PoC-2"])

    def test_start_command_uses_argument_list_for_database(self):
        """Optional database selection never passes through a shell string."""
        config = DoorsClientConfig(r"C:\IBM\DOORS\doors.exe", database="36677@doors.example")

        command = DoorsOleTransport(config).start_command()

        self.assertEqual(command, [r"C:\IBM\DOORS\doors.exe", "-d", "36677@doors.example"])

    @override_settings(AW_USERNAME="unused", AW_PASSWORD="unused")
    def test_start_command_never_places_credentials_in_process_arguments(self):
        """The dedicated Windows session supplies authentication outside argv."""

        command = DoorsOleTransport(DoorsClientConfig("doors.exe")).start_command()

        self.assertEqual(command, ["doors.exe"])
        self.assertNotIn("-u", command)
        self.assertNotIn("-P", command)

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

    @patch("integrations.doors.services.sys.platform", "linux")
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
    """Verify durable DOORS API authorization, availability, and ownership."""

    def setUp(self):
        """Create authenticated callers and isolated private artifact storage."""

        self.media_directory = Path(tempfile.mkdtemp())
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory / "public",
            PRIVATE_MEDIA_ROOT=self.media_directory / "private",
        )
        self.settings_override.enable()
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="doors-user")
        self.other_user = get_user_model().objects.create_user(username="doors-other")
        self.admin = get_user_model().objects.create_superuser(username="doors-admin")
        self.client.force_authenticate(self.user)

    def tearDown(self):
        """Remove isolated job artifacts."""

        self.settings_override.disable()
        shutil.rmtree(self.media_directory, ignore_errors=True)

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_status_never_returns_database_or_credentials(self, bridge_status):
        """DOORS readiness output contains only non-secret bridge state."""

        bridge_status.return_value = self.bridge_state(available=True)

        response = self.client.get(reverse("doors_status"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "configured": True,
                "available": True,
                "active_agents": 1,
                "transport": "outbound_https_mtls",
            },
        )
        self.assertNotIn("database", response.data)
        self.assertNotIn("password", response.data)

    @override_settings(DOORS_ENABLED=False)
    @patch("automations.bridge.bridge_status")
    def test_disabled_integration_stays_unavailable_when_bridge_is_live(self, bridge_status):
        """A live generic bridge cannot bypass the DOORS feature flag."""

        bridge_status.return_value = self.bridge_state(available=True)

        status_response = self.client.get(reverse("doors_status"))
        create_response = self.enqueue_module("doors-disabled-1")

        self.assertEqual(status_response.status_code, 200)
        self.assertFalse(status_response.data["configured"])
        self.assertFalse(status_response.data["available"])
        self.assertEqual(status_response.data["active_agents"], 0)
        self.assertEqual(create_response.status_code, 503)
        self.assertEqual(create_response.data["code"], "WINDOWS_BRIDGE_UNAVAILABLE")
        self.assertFalse(Job.objects.exists())

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_module_check_creates_credential_free_private_job(self, bridge_status):
        """HTTP serializes an allowlisted operation and never invokes COM."""

        bridge_status.return_value = self.bridge_state(available=True)

        with patch("integrations.doors.services.execute_with_client") as execute_client:
            response = self.enqueue_module("doors-module-1")

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get()
        self.assertEqual(job.owner, self.user)
        self.assertEqual(job.kind, "doors.run_dxl")
        self.assertIn(f"jobs/{self.user.pk}/{job.pk}/", job.input_file.name)
        with job.input_file.open("rb") as artifact:
            payload = json.load(artifact)
        self.assertEqual(
            payload,
            {"module_path": "/Project/Module", "operation": "check_module"},
        )
        self.assertNotRegex(json.dumps(payload), r"password|credential|username|token")
        execute_client.assert_not_called()

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_read_routes_persist_only_their_allowlisted_operation(self, bridge_status):
        """Each read route emits its fixed operation rather than caller-selected DXL."""

        bridge_status.return_value = self.bridge_state(available=True)
        cases = [
            (
                "doors_module_export_job",
                {"module_path": "/Project/Module", "limit": 10000},
                "export_module",
            ),
            (
                "doors_object_list_job",
                {
                    "module_path": "/Project/Module",
                    "attributes": ["Object Text"],
                    "loop": "entire",
                    "limit": 25,
                },
                "list_objects",
            ),
            (
                "doors_object_detail_job",
                {"module_path": "/Project/Module", "absolute_number": 42},
                "get_object",
            ),
            (
                "doors_discipline_check_job",
                {"module_path": "/Project/Module"},
                "check_applicable_disciplines",
            ),
        ]

        for index, (route, payload, operation) in enumerate(cases, start=1):
            with self.subTest(route=route):
                response = self.client.post(
                    reverse(route),
                    payload,
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=f"doors-read-{index}",
                )
                self.assertEqual(response.status_code, 201)
                job = Job.objects.get(pk=response.data["id"])
                with job.input_file.open("rb") as artifact:
                    stored = json.load(artifact)
                self.assertEqual(stored.pop("operation"), operation)
                self.assertNotRegex(json.dumps(stored), r"password|credential|username|token")

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_idempotent_replay_is_owner_scoped(self, bridge_status):
        """Exact retries replay per owner while another owner gets a new job."""

        bridge_status.return_value = self.bridge_state(available=True)

        first = self.enqueue_module("doors-replay-1")
        replay = self.enqueue_module("doors-replay-1")
        first_job = Job.objects.get(owner=self.user)
        self.client.force_authenticate(self.other_user)
        other = self.enqueue_module("doors-replay-1")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(other.status_code, 201)
        self.assertEqual(Job.objects.count(), 2)
        detail = self.client.get(reverse("job_detail", args=[first_job.id]))
        self.assertEqual(detail.status_code, 404)

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_idempotency_key_cannot_be_reused_for_different_input(self, bridge_status):
        """One owner cannot alias two different operations to the same request key."""

        bridge_status.return_value = self.bridge_state(available=True)
        self.enqueue_module("doors-conflict-1")

        response = self.client.post(
            reverse("doors_module_check_job"),
            {"module_path": "/Project/Other"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="doors-conflict-1",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(Job.objects.count(), 1)

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_enqueue_requires_live_bridge_and_idempotency_key(self, bridge_status):
        """No unclaimable job or keyless external operation enters the queue."""

        bridge_status.return_value = self.bridge_state(available=False)
        unavailable = self.enqueue_module("doors-unavailable-1")
        bridge_status.return_value = self.bridge_state(available=True)
        keyless = self.client.post(
            reverse("doors_module_check_job"),
            {"module_path": "/Project/Module"},
            format="json",
        )

        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.data["code"], "WINDOWS_BRIDGE_UNAVAILABLE")
        self.assertEqual(keyless.status_code, 400)
        self.assertEqual(keyless.data["code"], "IDEMPOTENCY_KEY_REQUIRED")
        self.assertFalse(Job.objects.exists())

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_enqueue_rejects_unknown_credential_fields(self, bridge_status):
        """Credentials cannot be silently accepted or persisted with an operation."""

        bridge_status.return_value = self.bridge_state(available=True)

        response = self.client.post(
            reverse("doors_module_check_job"),
            {"module_path": "/Project/Module", "password": "not-accepted"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="doors-unknown-1",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        self.assertNotIn("not-accepted", json.dumps(response.data))
        self.assertFalse(Job.objects.exists())

    @override_settings(DOORS_ENABLED=True, WINDOWS_BRIDGE_MAX_INPUT_BYTES=16)
    @patch("automations.bridge.bridge_status")
    def test_enqueue_rejects_artifacts_the_bridge_cannot_claim(self, bridge_status):
        """The HTTP boundary and Windows bridge enforce the same payload limit."""

        bridge_status.return_value = self.bridge_state(available=True)

        response = self.enqueue_module("doors-size-limit-1")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "DOORS_OPERATION_PAYLOAD_LIMIT")
        self.assertFalse(Job.objects.exists())

    def test_object_update_requires_administrator(self):
        """A normal authenticated user cannot mutate DOORS objects."""

        response = self.client.post(
            reverse("doors_object_update_job"),
            {
                "module_path": "/Project/Module",
                "absolute_number": 42,
                "attributes": {"Status": "Approved"},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="doors-update-1",
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_administrator_can_queue_validated_object_update(self, bridge_status):
        """An administrator mutation becomes a durable operation-specific job."""

        bridge_status.return_value = self.bridge_state(available=True)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse("doors_object_update_job"),
            {
                "module_path": "/Project/Module",
                "absolute_number": 42,
                "attributes": {"Status": "Approved"},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="doors-update-2",
        )

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get()
        self.assertEqual(job.kind, "doors.update_object")
        with job.input_file.open("rb") as artifact:
            payload = json.load(artifact)
        self.assertEqual(payload["absolute_number"], 42)
        self.assertNotIn("operation", payload)

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_administrator_can_queue_validated_object_create(self, bridge_status):
        """Object creation is an explicit durable write with scalar-only input."""

        bridge_status.return_value = self.bridge_state(available=True)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse("doors_object_create_job"),
            {
                "module_path": "/Project/Module",
                "position": "after",
                "relative_absolute_number": 42,
                "attributes": {"Object Heading": "New requirement"},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="doors-create-1",
        )

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get()
        self.assertEqual(job.kind, "doors.create_object")
        with job.input_file.open("rb") as artifact:
            payload = json.load(artifact)
        self.assertEqual(payload["relative_absolute_number"], 42)
        self.assertNotIn("operation", payload)

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_authenticated_user_can_queue_link_preview(self, bridge_status):
        """Show mode remains available without granting an external write."""

        bridge_status.return_value = self.bridge_state(available=True)
        response = self.enqueue_linker("doors-link-preview-1", activeness=False)

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get()
        self.assertEqual(job.kind, "doors.link_requirements")
        self.assertFalse(job.reconcile_on_lease_loss)
        with job.input_file.open("rb") as artifact:
            payload = json.load(artifact)
        self.assertFalse(payload["activeness"])
        self.assertEqual(payload["direction"], "ref2tar")
        self.assertNotRegex(json.dumps(payload), r"password|credential|username|token")

    def test_link_creation_requires_administrator(self):
        """A regular authenticated user cannot queue the DOORS write mode."""

        response = self.enqueue_linker("doors-link-denied-1", activeness=True)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "DOORS_LINK_PERMISSION_REQUIRED")
        self.assertFalse(Job.objects.exists())

    @override_settings(DOORS_ENABLED=True)
    @patch("automations.bridge.bridge_status")
    def test_administrator_can_queue_fenced_link_creation(self, bridge_status):
        """Link mode is durable and reconciles an uncertain Windows outcome."""

        bridge_status.return_value = self.bridge_state(available=True)
        self.client.force_authenticate(self.admin)
        response = self.enqueue_linker("doors-link-active-1", activeness=True)

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get()
        self.assertTrue(job.reconcile_on_lease_loss)
        self.assertEqual(job.kind, "doors.link_requirements")

    def test_legacy_synchronous_routes_are_absent(self):
        """No browser route can directly invoke COM or arbitrary DXL."""

        paths = [
            "/api/integrations/doors/run_dxl/",
            "/api/integrations/doors/application-result/probe/",
            "/api/integrations/doors/modules/check/",
            "/api/integrations/doors/objects/",
            "/api/integrations/doors/objects/detail/",
            "/api/integrations/doors/objects/update/",
            "/api/integrations/doors/objects/create/",
            "/api/integrations/doors/checklist/check_applicable_disciplines/",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, {}, format="json").status_code, 404)

    def test_script_generator_returns_escaped_canonical_json(self):
        """Workbook data and attribute names remain inside escaped DXL literals."""

        workbook = self.workbook_upload(
            ["Search Key", "Source Text"],
            [['REQ-"1"\nunsafe', 'value"; delete all']],
        )
        response = self.client.post(
            reverse("script"),
            {
                "file": workbook,
                "json": json.dumps(
                    [
                        {"excel": "Search Key", "doors": 'Identifier"', "search": True},
                        {"excel": "Source Text", "doors": "Object Text", "search": False},
                    ]
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"script", "row_count", "mapping_count"})
        self.assertEqual(response.data["row_count"], 1)
        self.assertEqual(response.data["mapping_count"], 2)
        self.assertIn(r'"Identifier\""', response.data["script"])
        self.assertIn(r'"REQ-\"1\"\nunsafe"', response.data["script"])
        self.assertIn(r'"value\"; delete all"', response.data["script"])

    def test_script_generator_rejects_ambiguous_or_missing_mappings(self):
        """Exactly one unique search key must resolve to a workbook column."""

        no_search = self.client.post(
            reverse("script"),
            {
                "file": self.workbook_upload(["Key"], [["REQ-1"]]),
                "json": json.dumps(
                    [{"excel": "Key", "doors": "Identifier", "search": False}]
                ),
            },
            format="multipart",
        )
        missing_header = self.client.post(
            reverse("script"),
            {
                "file": self.workbook_upload(["Key"], [["REQ-1"]]),
                "json": json.dumps(
                    [{"excel": "Missing", "doors": "Identifier", "search": True}]
                ),
            },
            format="multipart",
        )

        self.assertEqual(no_search.status_code, 400)
        self.assertEqual(no_search.data["code"], "VALIDATION_ERROR")
        self.assertEqual(missing_header.status_code, 400)
        self.assertEqual(missing_header.data["code"], "DOORS_SCRIPT_MAPPING_INVALID")
        self.assertNotIn("Missing", missing_header.data["detail"])

    def test_script_generator_sanitizes_workbook_parser_failures(self):
        """Malformed OOXML internals never reach the API response."""

        archive = BytesIO()
        with ZipFile(archive, "w", ZIP_DEFLATED) as workbook:
            workbook.writestr("xl/workbook.xml", "<sensitive-parser-input")
        upload = SimpleUploadedFile(
            "malformed.xlsx",
            archive.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(
            reverse("script"),
            {
                "file": upload,
                "json": json.dumps(
                    [{"excel": "Key", "doors": "Identifier", "search": True}]
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "DOORS_WORKBOOK_INVALID")
        self.assertNotIn("sensitive-parser-input", json.dumps(response.data))

    @patch("integrations.doors.views.MAX_SCRIPT_SOURCE_BYTES", 3)
    def test_script_generator_enforces_source_size_before_rendering(self):
        """Large selected cell content is rejected before a large script is built."""

        response = self.client.post(
            reverse("script"),
            {
                "file": self.workbook_upload(["Key"], [["REQ-1"]]),
                "json": json.dumps(
                    [{"excel": "Key", "doors": "Identifier", "search": True}]
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "DOORS_SCRIPT_SIZE_LIMIT")

    def enqueue_module(self, key):
        """Queue the canonical module-check request."""

        return self.client.post(
            reverse("doors_module_check_job"),
            {"module_path": "/Project/Module"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def enqueue_linker(self, key, *, activeness):
        """Queue the canonical Requirement PoC Linker request."""

        return self.client.post(
            reverse("doors_requirement_link_job"),
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
                "activeness": activeness,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    @staticmethod
    def bridge_state(available):
        """Return a complete non-secret bridge state fixture."""

        return {
            "configured": True,
            "enabled": available,
            "available": available,
            "active_agents": 1 if available else 0,
            "queue": "windows",
            "transport": "outbound_https_mtls",
            "database_access": "none",
            "cache_access": "none",
        }

    @staticmethod
    def workbook_upload(headers, rows):
        """Build a signature-valid in-memory OOXML workbook."""

        from openpyxl import Workbook

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(headers)
        for row in rows:
            worksheet.append(row)
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return SimpleUploadedFile(
            "doors-input.xlsx",
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
