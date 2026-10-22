from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from integrations.assessment import AssessmentServiceError
from ddf.models import DDF


class DDFPermissionTests(TestCase):
    """Verify DDF endpoints do not expose user-specific data anonymously."""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user("ddf-user", password="pass")
        self.ddf = DDF.objects.create(
            project="Project",
            doc_name="Document",
            doc_no="DOC-1",
            doc_issue="A",
            date="2026-06-17",
            commentor="Owner",
            comments=[],
            created_by=self.user,
        )

    def test_anonymous_requests_are_rejected(self):
        endpoints = [
            ("get", "/api/tools/ddf/", None),
            ("post", "/api/tools/ddf/", {}),
            ("delete", "/api/tools/ddf/", None),
            ("get", f"/api/tools/ddf/{self.ddf.pk}/", None),
            ("put", f"/api/tools/ddf/{self.ddf.pk}/", {}),
            ("patch", f"/api/tools/ddf/{self.ddf.pk}/", {}),
            ("delete", f"/api/tools/ddf/{self.ddf.pk}/", None),
            ("post", "/api/tools/ddf/upload/", {}),
            (
                "post",
                "/api/tools/ddf/assessment/",
                {"id": self.ddf.pk, "comments": []},
            ),
        ]
        for method, path, payload in endpoints:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, payload, format="json")
                self.assertIn(response.status_code, [401, 403])

    def test_authenticated_user_cannot_read_another_users_ddf(self):
        other = get_user_model().objects.create_user("other-ddf-user", password="pass")
        other.user_permissions.add(Permission.objects.get(codename="view_ddf"))
        self.client.force_authenticate(user=other)

        response = self.client.get(f"/api/tools/ddf/{self.ddf.pk}/")

        self.assertEqual(response.status_code, 403)

    @patch("ddf.views.request_assessment", return_value="Teknik Görüş")
    def test_assessment_uses_bounded_client_and_persists_result(self, assessment):
        """The endpoint delegates transport policy and stores only parsed classifications."""

        self.user.user_permissions.add(Permission.objects.get(codename="change_ddf"))
        self.client.force_authenticate(user=self.user)
        comments = [["1", "Authority", "Review the requirement"]]

        self.ddf.comments = comments
        self.ddf.save(update_fields=["comments"])
        response = self.client.post(
            "/api/tools/ddf/assessment/",
            {"id": self.ddf.pk, "comments": comments},
            format="json",
        )

        self.ddf.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, ["[Teknik Görüş] Review the requirement"])
        self.assertEqual(self.ddf.comment_types, ["Teknik Görüş"])
        payload = assessment.call_args.args[0]
        self.assertIsInstance(payload, str)
        self.assertIn("Review the requirement", payload)

    @patch("ddf.views.request_assessment")
    def test_assessment_failure_uses_sanitized_contract(self, assessment):
        """Upstream failures expose stable codes instead of internal exception details."""

        assessment.side_effect = AssessmentServiceError(
            "The assessment service rejected the request.",
            "ASSESSMENT_UPSTREAM_REJECTED",
            502,
        )
        self.user.user_permissions.add(Permission.objects.get(codename="change_ddf"))
        self.client.force_authenticate(user=self.user)

        self.ddf.comments = [['1', 'Authority', 'Sensitive comment']]
        self.ddf.save(update_fields=["comments"])
        response = self.client.post(
            "/api/tools/ddf/assessment/",
            {
                "id": self.ddf.pk,
                "comments": [["1", "Authority", "Sensitive comment"]],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "ASSESSMENT_UPSTREAM_REJECTED")
        self.assertEqual(
            response.data["detail"],
            "The assessment service rejected the request.",
        )

    @patch("ddf.views.request_assessment")
    def test_multiline_classifications_preserve_all_comments(self, assessment):
        self.user.user_permissions.add(Permission.objects.get(codename="change_ddf"))
        self.client.force_authenticate(user=self.user)
        assessment.return_value = "Teknik Görüş,\n Bilgi Görüşü"
        comments = [["1", "Authority", "First"], ["2", "Authority", "Second"]]
        self.ddf.comments = comments
        self.ddf.save(update_fields=["comments"])
        response = self.client.post(
            "/api/tools/ddf/assessment/",
            {"id": self.ddf.pk, "comments": comments},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, ["[Teknik Görüş] First", "[Bilgi Görüşü] Second"])
        self.ddf.refresh_from_db()
        self.assertEqual(self.ddf.comment_types, ["Teknik Görüş", "Bilgi Görüşü"])

    @patch("ddf.views.request_assessment", return_value="Teknik Görüş")
    def test_wrong_classification_count_does_not_overwrite_saved_result(self, assessment):
        self.user.user_permissions.add(Permission.objects.get(codename="change_ddf"))
        self.client.force_authenticate(user=self.user)
        self.ddf.comment_types = ["Bilgi Görüşü"]
        self.ddf.save(update_fields=["comment_types"])
        self.ddf.comments = [['1', 'Authority', 'First'], ['2', 'Authority', 'Second']]
        self.ddf.save(update_fields=["comments"])
        response = self.client.post(
            "/api/tools/ddf/assessment/",
            {"id": self.ddf.pk, "comments": [["1", "Authority", "First"], ["2", "Authority", "Second"]]},
            format="json",
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "ASSESSMENT_RESPONSE_INVALID")
        self.ddf.refresh_from_db()
        self.assertEqual(self.ddf.comment_types, ["Bilgi Görüşü"])

    @patch("ddf.views.request_assessment", return_value="Teknik Görüş, Bilgi Görüşü")
    def test_private_prompt_preserves_comment_order_and_excludes_record_metadata(self, assessment):
        from awcenter.workflow_test_utils import private_workflow_configuration
        with private_workflow_configuration():
            self.user.user_permissions.add(Permission.objects.get(codename="change_ddf"))
            self.client.force_authenticate(user=self.user)
            comments = [["1", "Section A", "First synthetic comment"], ["2", "Section B", "Second synthetic comment"]]
            self.ddf.comments = comments
            self.ddf.save(update_fields=["comments"])
            response = self.client.post("/api/tools/ddf/assessment/", {"id": self.ddf.pk, "comments": comments}, format="json")
        self.assertEqual(response.status_code, 200)
        expected = "Synthetic classification instructions.\nComments:\n        " + str([
            "\n1) First synthetic comment\n", "\n2) Second synthetic comment\n",
        ])
        self.assertEqual(assessment.call_args.args[0], expected)
        self.ddf.refresh_from_db()
        self.assertEqual(self.ddf.comment_types, ["Teknik Görüş", "Bilgi Görüşü"])
        self.assertEqual(self.ddf.doc_no, "DOC-1")
        self.assertEqual(self.ddf.project, "Project")
        self.assertEqual(self.ddf.created_by_id, self.user.pk)

    @patch("ddf.views.request_assessment")
    def test_missing_private_prompt_does_not_send_or_overwrite_saved_classification(self, assessment):
        from django.test import override_settings
        self.user.user_permissions.add(Permission.objects.get(codename="change_ddf"))
        self.client.force_authenticate(user=self.user)
        self.ddf.comment_types = ["Bilgi Görüşü"]
        self.ddf.save(update_fields=["comment_types"])
        with override_settings(DDF_ASSESSMENT_POLICY_FILE=""):
            self.ddf.comments = [['1', 'Section', 'Synthetic comment']]
            self.ddf.save(update_fields=["comments"])
            response = self.client.post("/api/tools/ddf/assessment/", {
                "id": self.ddf.pk, "comments": [["1", "Section", "Synthetic comment"]],
            }, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "DDF_POLICY_UNAVAILABLE")
        assessment.assert_not_called()
        self.ddf.refresh_from_db()
        self.assertEqual(self.ddf.comment_types, ["Bilgi Görüşü"])

    @patch("ddf.views.request_assessment")
    def test_invalid_private_prompt_keeps_saved_data_and_returns_sanitized_error(self, assessment):
        import json
        from pathlib import Path
        from awcenter.workflow_test_utils import private_workflow_configuration
        self.user.user_permissions.add(Permission.objects.get(codename="change_ddf"))
        self.client.force_authenticate(user=self.user)
        with private_workflow_configuration() as files:
            path = Path(files["DDF_ASSESSMENT_POLICY_FILE"])
            for prefix in (None, "", [], {}):
                with self.subTest(prefix_type=type(prefix).__name__):
                    path.write_text(json.dumps({"schema_version": 1, "prompt_prefix": prefix}))
                    self.ddf.comments = [['1', 'Section', 'Synthetic comment']]
                    self.ddf.save(update_fields=["comments"])
                    response = self.client.post("/api/tools/ddf/assessment/", {
                        "id": self.ddf.pk, "comments": [["1", "Section", "Synthetic comment"]],
                    }, format="json")
                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn(str(path), str(response.data))
        assessment.assert_not_called()
        self.ddf.refresh_from_db()
        self.assertEqual(self.ddf.comment_types, [])
        self.assertEqual(self.ddf.created_by_id, self.user.pk)

    @patch("ddf.views.assessment_prompt")
    @patch("ddf.views.request_assessment")
    def test_other_owner_is_rejected_before_private_prompt_or_ai_access(self, assessment, prompt):
        other = get_user_model().objects.create_user("ddf-outsider", password="pass")
        other.user_permissions.add(Permission.objects.get(codename="change_ddf"))
        self.client.force_authenticate(user=other)
        self.ddf.comments = [['1', 'Section', 'Synthetic comment']]
        self.ddf.save(update_fields=["comments"])
        response = self.client.post("/api/tools/ddf/assessment/", {
            "id": self.ddf.pk, "comments": [["1", "Section", "Synthetic comment"]],
        }, format="json")
        self.assertEqual(response.status_code, 403)
        prompt.assert_not_called()
        assessment.assert_not_called()
