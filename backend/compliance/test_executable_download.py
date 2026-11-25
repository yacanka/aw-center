"""The reader locator is inert data, private per response and authorized at download."""

import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase as UnitTestCase

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from orgs.models import Project, ProjectRoleAssignment
from .executable_config import (
    database_path_trailer, embedded_configuration, mark_executable_template, validate_database_path,
)
from .executable_download import ExecutableResponse


def write_test_template(path):
    # Only the PE header and archive cookie are used by the publisher and reader.
    header = b"MZ" + bytes(58) + (64).to_bytes(4, "little") + b"PE\0\0"
    cookie = struct.pack("!8sIIII64s", b"MEI\014\013\012\013\016", 89, 0, 1, 311, b"python311.dll")
    path.write_bytes(header + b"x" + cookie)
    mark_executable_template(path)


class DashboardLocatorTests(UnitTestCase):
    def test_windows_path_validation(self):
        for raw in (r"Z:\Görev\dosya.db", r"\\server-2.example\shared files\db.SQLITE3"):
            self.assertEqual(validate_database_path(raw.replace("\\", "/")), raw)
        for invalid in (
            "", None, [], r"C:relative.db", r"..\db.sqlite", r"C:\..\db.sqlite", r"C:\.\db.sqlite",
            r"c:\folder.\a.db", r"C:\foo  \a.db", r"C:\COM2\a.db", r"C:\LPT².tmp\a.db",
            r"C:\secret:db.sqlite", r"\\.\C:\db.sqlite", r"\\?\UNC\host\share\db.sqlite",
            r"\\host\DavWWWRoot\db.sqlite", r"\\host@SSL\share\db.sqlite", r"\\host\pipe\a.db",
            r"C:\folder\report.exe", "C:\\folder\\bad\nname.sqlite", r"C:\NUL .sqlite",
            r"C:\folder\a?.sqlite3", r"\\host\a.sqlite", "C:\\" + "a" * 256 + ".db",
            "C:\\" + "\\unreasonably_long_directory" * 200 + "\\db.sqlite3",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_database_path(invalid)

    def test_template_cannot_be_used_as_configured_reader_or_restamped_after_configuration(self):
        with TemporaryDirectory() as directory:
            exe = Path(directory) / "test.exe"
            write_test_template(exe)
            template = exe.read_bytes()
            mark_executable_template(exe)
            self.assertEqual(exe.read_bytes(), template)
            with self.assertRaises(ValueError):
                embedded_configuration(exe)
            configured = template + database_path_trailer(r"C:\db.sqlite3")
            exe.write_bytes(configured)
            self.assertEqual(embedded_configuration(exe), (r"C:\db.sqlite3", False))
            with self.assertRaises(ValueError):
                mark_executable_template(exe)
            for corrupt in (configured[:-1], b"MZ", b"not-a-template" + configured[len(template):]):
                exe.write_bytes(corrupt)
                with self.assertRaises(ValueError):
                    embedded_configuration(exe)

    def test_asgi_stream_is_async_bounded_and_releases_template(self):
        async def collect(response):
            return [chunk async for chunk in response]
        with TemporaryDirectory() as directory:
            exe = Path(directory) / "reader.exe"
            exe.write_bytes(bytes(300 * 1024))
            stream = exe.open("rb")
            response = ExecutableResponse(stream, exe.stat().st_size, b"path", asynchronous=True)
            self.assertTrue(response.is_async)
            self.assertEqual(list(map(len, async_to_sync(collect)(response))), [262144, 45056, 4])
            response.close()
            self.assertTrue(stream.closed)


class DashboardExecutableApiTests(TestCase):
    url = "/api/projects/ozgur/compliance-documents/dashboard/executable/"

    def setUp(self):
        self.user = get_user_model().objects.create_user("reader")
        self.client = APIClient()
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.template = Path(self.directory.name) / "template.exe"
        write_test_template(self.template)
        setting = self.settings(DASHBOARD_EXECUTABLE_TEMPLATE=self.template, AWCENTER_DASHBOARD_SHARES=())
        setting.enable()
        self.addCleanup(setting.disable)

    def grant_role(self):
        ProjectRoleAssignment.objects.create(
            project=Project.objects.get(slug="ozgur"), user=self.user, domain="compliance", role="viewer"
        )

    def post(self, path):
        return self.client.post(self.url, {"database_path": path}, format="json")

    def test_session_project_capability_and_csrf(self):
        body = {"database_path": r"C:\db.sqlite3"}
        self.assertEqual(self.post(body["database_path"]).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.post(body["database_path"]).data["code"], "PROJECT_ROLE_REQUIRED")
        self.grant_role()
        enforcing = APIClient(enforce_csrf_checks=True)
        enforcing.force_login(self.user)
        self.assertEqual(enforcing.post(self.url, body, format="json").status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.url.replace("ozgur", "missing"), body, format="json").status_code, 404)

    def test_request_local_attachment_has_no_database_bytes_and_unc_requires_consent_unless_listed(self):
        self.grant_role()
        self.client.force_login(self.user)
        template = self.template.read_bytes()
        cases = (
            (r"C:\Grup\işler.sqlite3", False),
            (r"\\files\approved\db.sqlite3", True),
            (r"\\files\approved2\db.sqlite3", False),
            (r"\\other\approved\db.sqlite3", False),
        )
        with self.settings(AWCENTER_DASHBOARD_SHARES=(r"\\FILES\Approved",)):
            responses = [self.post(path) for path, _ in cases]
        for response, (path, expected_trust) in zip(responses, cases):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Disposition"], 'attachment; filename="CertificationDashboard.exe"')
            self.assertEqual(response["Cache-Control"], "private, no-store")
            content = b"".join(response.streaming_content)
            self.assertEqual(int(response["Content-Length"]), len(content))
            self.assertTrue(content.startswith(template))
            self.assertLessEqual(len(content) - len(template), 4096)
            downloaded = self.template.with_name("downloaded.exe")
            downloaded.write_bytes(content)
            self.assertEqual(embedded_configuration(downloaded), (path, expected_trust))
        self.assertEqual(self.template.read_bytes(), template)

    def test_errors_are_bounded_and_do_not_disclose_paths(self):
        self.grant_role()
        self.client.force_login(self.user)
        invalid = r"C:\private\..\db.sqlite3"
        bad = self.post(invalid)
        self.assertEqual(bad.data["code"], "INVALID_DATABASE_PATH")
        self.assertNotIn("private", bad.data["detail"])
        self.template.write_bytes(b"incorrect or outdated executable")
        for path in (self.template, self.template.with_name("missing")):
            with self.settings(DASHBOARD_EXECUTABLE_TEMPLATE=path):
                unavailable = self.post(r"C:\private\db.sqlite3")
            self.assertEqual(unavailable.status_code, 503)
            self.assertEqual(unavailable.data["code"], "DASHBOARD_EXECUTABLE_UNAVAILABLE")
            self.assertNotIn(str(path), str(unavailable.data))
