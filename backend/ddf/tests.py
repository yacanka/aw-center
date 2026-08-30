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

    @patch("ddf.views.request_assessment", return_value=["Teknik Görüş"])
    def test_assessment_uses_bounded_client_and_persists_result(self, assessment):
        """The endpoint delegates transport policy and stores only parsed classifications."""

        self.user.user_permissions.add(Permission.objects.get(codename="add_ddf"))
        self.client.force_authenticate(user=self.user)
        comments = [["1", "Authority", "Review the requirement"]]

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
        self.assertEqual(payload["chat_purpose"], 1)
        self.assertNotIn("url", payload)

    @patch("ddf.views.request_assessment")
    def test_assessment_failure_uses_sanitized_contract(self, assessment):
        """Upstream failures expose stable codes instead of internal exception details."""

        assessment.side_effect = AssessmentServiceError(
            "The assessment service rejected the request.",
            "ASSESSMENT_UPSTREAM_REJECTED",
            502,
        )
        self.user.user_permissions.add(Permission.objects.get(codename="add_ddf"))
        self.client.force_authenticate(user=self.user)

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
