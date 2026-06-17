from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

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
            ("get", "/ddf/", None),
            ("post", "/ddf/", {}),
            ("delete", "/ddf/", None),
            ("get", f"/ddf/{self.ddf.pk}/", None),
            ("put", f"/ddf/{self.ddf.pk}/", {}),
            ("patch", f"/ddf/{self.ddf.pk}/", {}),
            ("delete", f"/ddf/{self.ddf.pk}/", None),
            ("post", "/ddf/upload/", {}),
            ("post", "/ddf/assessment/", {"id": self.ddf.pk, "comments": []}),
        ]
        for method, path, payload in endpoints:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, payload, format="json")
                self.assertIn(response.status_code, [401, 403])

    def test_authenticated_user_cannot_read_another_users_ddf(self):
        other = get_user_model().objects.create_user("other-ddf-user", password="pass")
        other.user_permissions.add(Permission.objects.get(codename="view_ddf"))
        self.client.force_authenticate(user=other)

        response = self.client.get(f"/ddf/{self.ddf.pk}/")

        self.assertEqual(response.status_code, 403)
