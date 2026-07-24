"""Characterization tests for DCC helper behavior."""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from dcc.models import JIRA_DCC

from dcc.service.JIRAConnector import JiraConnector
from dcc.service.effectivity import match_effectivity_options, normalize_effectivity_text
from dcc.service.reminder_rate_limit import reserve_reminder_email_slot
from dcc.serializers import JIRA_DCC_Serializer
from dcc.services.jira_links import attach_jira_issue_urls, build_jira_issue_url
from dcc.service.text_parsing import (
    check_panel_text,
    classify_dcc,
    extract_text_from_text,
    find_keyword_list2d,
    make_surname_upper,
    multiselect_to_text,
    normalize_filename,
    parse_labels,
    parse_multiselect,
)


class DccTextParsingTests(SimpleTestCase):
    """Protect legacy parsing behavior while DCC views are decomposed."""

    def test_parse_labels_normalizes_semicolon_separated_values(self):
        self.assertEqual(
            parse_labels(" ATA 21 ;Flight Control; ;ATA 21"),
            ["ata_21", "flight_control", "ata_21"],
        )

    def test_parse_multiselect_keeps_first_case_insensitive_unique_value(self):
        self.assertEqual(
            parse_multiselect("A320 ; a320; A330; ;A330 "),
            [{"value": "A320"}, {"value": "A330"}],
        )

    def test_multiselect_to_text_accepts_legacy_value_shapes(self):
        values = [{"value": " A "}, SimpleNamespace(value="B"), " C ", None, {"value": ""}]
        self.assertEqual(multiselect_to_text(values), "A, B, C")

    def test_multiselect_to_text_wraps_single_object(self):
        self.assertEqual(multiselect_to_text(SimpleNamespace(value="A350")), "A350")

    def test_extract_text_from_text_matches_legacy_marker_rules(self):
        text = "before [start]middle[end] after"
        self.assertEqual(extract_text_from_text(text, "[start]", "[end]"), "middle")
        self.assertEqual(extract_text_from_text(text, "[start]"), "middle[end] after")
        self.assertEqual(extract_text_from_text(text, search_text2="[end]"), "before [start]middle")

    def test_panel_name_filename_and_coordinate_helpers_keep_legacy_behavior(self):
        self.assertTrue(check_panel_text("Panel 12. Description"))
        self.assertEqual(make_surname_upper("Ada Lovelace"), "Ada LOVELACE")
        self.assertEqual(normalize_filename(" A-– B "), "AB")
        self.assertEqual(find_keyword_list2d([["a"], ["b", "needle"]], "needle"), (1, 1))

    def test_classify_dcc_returns_highest_priority_known_classification(self):
        assignee = SimpleNamespace(displayName="Certification Owner")
        classification = [("Minor-No Effect", None), ("Major", assignee), ("Unknown", None)]
        self.assertEqual(classify_dcc(classification), ("Major", assignee))
        self.assertEqual(classify_dcc([("Unknown", None)]), (None, None))

    def test_normalize_effectivity_reorders_single_group(self):
        self.assertEqual(normalize_effectivity_text("4-5431 (1BC)"), "1BC 4-5431")

    def test_normalize_effectivity_expands_multiple_group_values(self):
        self.assertEqual(
            normalize_effectivity_text("1-12, 50, 5431 (1BC)"),
            "1BC 1-12; 1BC-50; 1BC-5431",
        )

    def test_normalize_effectivity_handles_sequential_groups(self):
        self.assertEqual(
            normalize_effectivity_text("1-12, 80 (4AV) 9 (HC2) 1-9, 15-18 (AX2)"),
            "4AV 1-12; 4AV-80; HC2 9; AX2 1-9; AX2 15-18",
        )

    def test_match_effectivity_options_uses_closest_allowed_values(self):
        options = [{"value": "4AV 1-12"}, {"value": "4AV-080"}, {"value": "HC2 9"}]
        self.assertEqual(
            match_effectivity_options("1-12, 80 (4AV) 9 (HC2)", options),
            "4AV 1-12; 4AV-080; HC2 9",
        )


class JiraConnectorSubtaskFieldTests(SimpleTestCase):
    """Verify dynamic sub-task payload construction without a JIRA server."""

    def test_build_subtask_fields_keeps_dynamic_custom_fields(self):
        connector = JiraConnector.__new__(JiraConnector)
        connector.issue_key = "DCC-42"

        fields = connector.build_subtask_fields(
            summary="Review document",
            assignee="engineer",
            duedate=2,
            extra_fields={"customfield_10010": "Safety", "customfield_10011": ""},
        )

        self.assertEqual(fields["summary"], "Review document")
        self.assertEqual(fields["customfield_10010"], "Safety")
        self.assertNotIn("customfield_10011", fields)
        self.assertEqual(fields["assignee"], {"name": "engineer"})

    def test_get_subtask_fields_returns_createmeta_field_descriptors(self):
        connector = JiraConnector.__new__(JiraConnector)
        connector.issue_key = "DCC-42"
        connector.jira = SimpleNamespace(createmeta=lambda **_: {
            "projects": [{"issuetypes": [{"fields": {
                "summary": {"name": "Summary", "required": True, "schema": {"type": "string"}},
            }}]}]
        })

        fields = connector.get_subtask_fields()

        self.assertEqual(fields[0]["id"], "summary")
        self.assertEqual(fields[0]["name"], "Summary")
        self.assertTrue(fields[0]["required"])

    def test_get_create_field_allowed_values_returns_target_field_options(self):
        connector = JiraConnector.__new__(JiraConnector)
        connector.jira = SimpleNamespace(createmeta=lambda **_: {
            "projects": [{"issuetypes": [{"fields": {
                "customfield_34115": {"allowedValues": [{"value": "4AV 1-12"}]},
            }}]}]
        })

        options = connector.get_create_field_allowed_values("CHN", "Task", "customfield_34115")

        self.assertEqual(options, [{"value": "4AV 1-12"}])


@override_settings(JIRA_URL="https://jira.example.test/root/")
class JiraIssueLinkTests(SimpleTestCase):
    """Verify browser links are generated only from backend JIRA settings."""

    def test_build_jira_issue_url_normalizes_base_and_encodes_key(self):
        """Configured base paths are preserved and issue values cannot alter the URL path."""

        self.assertEqual(
            build_jira_issue_url(" CHN/42 "),
            "https://jira.example.test/root/browse/CHN%2F42",
        )

    @override_settings(JIRA_URL="javascript:alert(1)")
    def test_build_jira_issue_url_rejects_unsafe_backend_configuration(self):
        """Frontend navigation never receives a non-HTTP URL from configuration."""

        with self.assertRaises(ImproperlyConfigured):
            build_jira_issue_url("CHN-42")

    def test_dcc_serializer_exposes_read_only_jira_issue_url(self):
        """DCC API rows include the backend-owned URL and ignore client overrides."""

        instance = SimpleNamespace(
            id=1, issue="CHN-42", ecd_name="Change", dcc_path="//", active=True
        )
        serialized = JIRA_DCC_Serializer(instance).data
        incoming = JIRA_DCC_Serializer(
            data={
                **serialized,
                "jira_issue_url": "javascript:alert(1)",
            }
        )

        self.assertEqual(
            serialized["jira_issue_url"],
            "https://jira.example.test/root/browse/CHN-42",
        )
        self.assertTrue(incoming.is_valid(), incoming.errors)
        self.assertNotIn("jira_issue_url", incoming.validated_data)

    def test_attach_jira_issue_urls_enriches_issue_and_subtasks(self):
        """Live JIRA payloads receive complete links for every navigable issue."""

        payload = {"key": "CHN-1", "fields": {"subtasks": [{"key": "CHN-2"}, {}]}}

        enriched = attach_jira_issue_urls(payload)

        self.assertEqual(enriched["jira_issue_url"], build_jira_issue_url("CHN-1"))
        self.assertEqual(
            enriched["fields"]["subtasks"][0]["jira_issue_url"],
            build_jira_issue_url("CHN-2"),
        )


class DccTemplateResolverTests(SimpleTestCase):
    """Verify secure resolution of project-specific DCC templates."""

    def setUp(self):
        from tempfile import TemporaryDirectory

        self.temporary_directory = TemporaryDirectory()
        self.template_directory = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_resolve_dcc_template_path_accepts_valid_template_name(self):
        """A plain existing .docx filename resolves under the template directory."""
        from unittest.mock import patch

        from dcc.services.template_resolver import resolve_dcc_template_path

        template_path = self.template_directory / "valid_template.docx"
        template_path.write_bytes(b"docx")
        project_definition = SimpleNamespace(dcc_template_name="valid_template.docx")

        with patch("dcc.services.template_resolver.TEMPLATE_DIR", self.template_directory):
            resolved_path = resolve_dcc_template_path(project_definition)

        self.assertEqual(resolved_path, template_path.resolve())

    def test_resolve_dcc_template_path_rejects_path_traversal(self):
        """Template names cannot escape the allowed template directory."""
        from dcc.services.template_resolver import (
            InvalidDccTemplateNameError,
            resolve_dcc_template_path,
        )

        project_definition = SimpleNamespace(dcc_template_name="../bad.docx")

        with self.assertRaises(InvalidDccTemplateNameError):
            resolve_dcc_template_path(project_definition)

    def test_resolve_dcc_template_path_rejects_wrong_extension(self):
        """Only .docx DCC templates are accepted."""
        from dcc.services.template_resolver import (
            InvalidDccTemplateNameError,
            resolve_dcc_template_path,
        )

        project_definition = SimpleNamespace(dcc_template_name="bad.pdf")

        with self.assertRaises(InvalidDccTemplateNameError):
            resolve_dcc_template_path(project_definition)

    def test_resolve_dcc_template_path_rejects_empty_value(self):
        """Empty template names fail before filesystem resolution."""
        from dcc.services.template_resolver import (
            InvalidDccTemplateNameError,
            resolve_dcc_template_path,
        )

        project_definition = SimpleNamespace(dcc_template_name=" ")

        with self.assertRaises(InvalidDccTemplateNameError):
            resolve_dcc_template_path(project_definition)


class DccReminderRateLimitTests(TestCase):
    """Verify per-record reminder email cooldown enforcement."""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user("reminder-user", password="pass")
        self.dcc = JIRA_DCC.objects.create(
            issue="DCC-REM-1",
            ecd_name="Reminder Change",
            dcc_path="//",
            active=True,
            created_by=self.user,
        )

    def test_reserve_reminder_email_slot_blocks_second_attempt_for_one_hour(self):
        first_wait = reserve_reminder_email_slot(self.dcc)
        second_wait = reserve_reminder_email_slot(self.dcc)

        self.assertEqual(first_wait, 0)
        self.assertGreater(second_wait, 0)

    def test_reserve_reminder_email_slot_allows_after_one_hour(self):
        self.dcc.last_reminder_mail_sent_at = timezone.now() - timedelta(hours=1, seconds=1)
        self.dcc.save(update_fields=["last_reminder_mail_sent_at"])

        wait_seconds = reserve_reminder_email_slot(self.dcc)

        self.assertEqual(wait_seconds, 0)

    def test_send_mail_returns_too_many_requests_inside_cooldown(self):
        self.dcc.last_reminder_mail_sent_at = timezone.now()
        self.dcc.save(update_fields=["last_reminder_mail_sent_at"])
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/dcc/send_mail/", {"issue": self.dcc.issue}, format="json")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "THROTTLED")
        self.assertIn("retry_after_seconds", response.data["errors"])


class DccPermissionTests(TestCase):
    """Verify DCC endpoints do not expose data to anonymous clients."""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user("dcc-user", password="pass")
        self.dcc = JIRA_DCC.objects.create(
            issue="DCC-1",
            ecd_name="Change",
            dcc_path="//",
            active=True,
            created_by=self.user,
        )

    def test_anonymous_requests_are_rejected(self):
        endpoints = [
            ("get", "/dcc/api/", None),
            ("get", f"/dcc/api/{self.dcc.pk}/", None),
            ("get", "/dcc/issues/", None),
            ("post", "/dcc/get_issue/", {}),
            ("post", "/dcc/create_issue/", {}),
            ("post", "/dcc/upload/", {}),
            ("post", "/dcc/ecd_assessment/", {}),
            ("post", "/dcc/send_mail/", {}),
            ("post", "/dcc/create_queue/", {}),
            ("post", "/dcc/subtask_fields/", {}),
            ("get", "/dcc/check_session/", None),
            ("post", "/dcc/add_attachment/", {}),
        ]
        for method, path, payload in endpoints:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, payload, format="json")
                self.assertIn(response.status_code, [401, 403])

    def test_dcc_api_accepts_boolean_query_filters(self):
        """Watcher filters must not raise validation errors for UI boolean values."""

        self.user.user_permissions.add(Permission.objects.get(codename="view_jira_dcc"))
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/dcc/api/", {"active": "true"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["issue"], self.dcc.issue)

    def test_authenticated_user_cannot_read_another_users_dcc(self):
        other = get_user_model().objects.create_user("other-dcc-user", password="pass")
        other.user_permissions.add(Permission.objects.get(codename="view_jira_dcc"))
        self.client.force_authenticate(user=other)

        response = self.client.get(f"/dcc/api/{self.dcc.pk}/")

        self.assertEqual(response.status_code, 403)

    def test_external_write_helpers_require_dcc_add_permission(self):
        """JIRA attachment and queue endpoints reject ordinary authenticated users."""

        self.client.force_authenticate(user=self.user)

        queue_response = self.client.post("/dcc/create_queue/", {}, format="json")
        attachment_response = self.client.post("/dcc/add_attachment/", {}, format="json")

        self.assertEqual(queue_response.status_code, 403)
        self.assertEqual(attachment_response.status_code, 403)

    def test_subtask_stream_queue_is_bound_to_creating_user(self):
        """A queue UUID cannot expose transient JIRA data to another DCC user."""

        add_permission = Permission.objects.get(codename="add_jira_dcc")
        view_permission = Permission.objects.get(codename="view_jira_dcc")
        self.user.user_permissions.add(add_permission, view_permission)
        self.client.force_authenticate(user=self.user)
        queued = self.client.post(
            "/dcc/create_queue/", {"JSESSIONID": "private", "url": "CHN-1"}, format="json"
        )

        other = get_user_model().objects.create_user("queue-other", password="pass")
        other.user_permissions.add(add_permission, view_permission)
        self.client.force_authenticate(user=other)
        denied = self.client.get(f"/dcc/create_subtask_stream/{queued.data}/")

        cache.delete(str(queued.data))
        self.assertEqual(queued.status_code, 200)
        self.assertEqual(denied.status_code, 404)


class DccProjectResolverTests(SimpleTestCase):
    """Verify DCC project resolution from JIRA component metadata."""

    def test_dcc_views_do_not_import_legacy_projects_enum(self):
        """DCC views must use registry-based project resolution, not legacy enums."""
        from pathlib import Path

        views_source = Path(__file__).with_name("views.py").read_text()

        self.assertNotIn("awcenter.enums import Projects", views_source)
        self.assertIn("resolve_project_from_jira_components", views_source)

    def test_resolve_project_from_jira_components_returns_first_known_project(self):
        """Multiple JIRA components are scanned until a registered project is found."""
        from dcc.services.project_resolver import resolve_project_from_jira_components

        components = [SimpleNamespace(name="Unrelated"), {"name": " aesa "}]

        project_definition = resolve_project_from_jira_components(components)

        self.assertEqual(project_definition.slug, "aesa")

    def test_resolve_project_from_jira_components_raises_for_unknown_components(self):
        """Unknown components fail with a controlled domain-specific exception."""
        from dcc.services.project_resolver import (
            UnknownDccProjectComponentError,
            resolve_project_from_jira_components,
        )

        with self.assertRaises(UnknownDccProjectComponentError):
            resolve_project_from_jira_components(["unknown", SimpleNamespace(name="other")])

    def test_resolve_project_from_jira_components_rejects_non_dcc_project(self):
        """Projects without the DCC capability cannot be selected for DCC."""
        from unittest.mock import patch

        from projects.types import ProjectDefinition

        from dcc.services.project_resolver import (
            DccCapabilityMissingError,
            resolve_project_from_jira_components,
        )

        project_definition = ProjectDefinition(
            slug="readonly",
            display_name="Read Only",
            app_label="projects.readonly",
            url_prefix="readonly",
            capabilities=("orgs",),
            jira_component="READONLY",
        )

        with patch(
            "dcc.services.project_resolver.find_project_by_jira_component",
            return_value=project_definition,
        ):
            with self.assertRaises(DccCapabilityMissingError):
                resolve_project_from_jira_components(["READONLY"])
