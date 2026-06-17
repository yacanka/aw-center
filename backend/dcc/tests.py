"""Characterization tests for DCC helper behavior."""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from dcc.models import JIRA_DCC

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
            ("get", "/dcc/test/", None),
            ("get", "/dcc/api/", None),
            ("get", f"/dcc/api/{self.dcc.pk}/", None),
            ("get", "/dcc/issues/", None),
            ("post", "/dcc/get_issue/", {}),
            ("post", "/dcc/create_issue/", {}),
            ("post", "/dcc/upload/", {}),
            ("post", "/dcc/ecd_assessment/", {}),
            ("post", "/dcc/send_mail/", {}),
            ("post", "/dcc/create_queue/", {}),
            ("get", "/dcc/check_session/", None),
            ("post", "/dcc/add_attachment/", {}),
        ]
        for method, path, payload in endpoints:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, payload, format="json")
                self.assertIn(response.status_code, [401, 403])

    def test_authenticated_user_cannot_read_another_users_dcc(self):
        other = get_user_model().objects.create_user("other-dcc-user", password="pass")
        other.user_permissions.add(Permission.objects.get(codename="view_jira_dcc"))
        self.client.force_authenticate(user=other)

        response = self.client.get(f"/dcc/api/{self.dcc.pk}/")

        self.assertEqual(response.status_code, 403)
