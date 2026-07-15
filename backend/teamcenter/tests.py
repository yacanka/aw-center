from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from requests.cookies import RequestsCookieJar
from rest_framework.test import APIClient

from .config import AuthMode, TeamcenterClientConfig
from .exceptions import TeamcenterConfigurationError, TeamcenterProtocolError, TeamcenterServiceError
from .protocol import make_envelope, raise_for_partial_errors
from .response import read_bounded_content
from .services import validate_transport_security
from .transport import TeamcenterTransport


class TeamcenterProtocolTests(SimpleTestCase):
    """Verify Teamcenter protocol and configuration behavior."""

    def test_envelope_contains_required_header_and_body(self):
        """SOA calls include empty state and policy headers."""
        envelope = make_envelope({"uids": ["UID-1"]})

        self.assertEqual(envelope["body"], {"uids": ["UID-1"]})
        self.assertEqual(envelope["header"], {"state": {}, "policy": {}})

    def test_partial_errors_raise_service_error(self):
        """Nested ServiceData partial errors cannot pass as success."""
        payload = {"ServiceData": {"partialErrors": [{"code": 42, "messages": ["Denied"]}]}}

        with self.assertRaises(TeamcenterServiceError):
            raise_for_partial_errors(payload)

    def test_password_configuration_requires_credentials(self):
        """Password mode fails closed when credentials are absent."""
        with self.assertRaises(TeamcenterConfigurationError):
            TeamcenterClientConfig(base_url="https://teamcenter.example/tc")

    def test_cookie_configuration_accepts_server_side_session(self):
        """Cookie mode accepts an explicitly configured JSESSIONID."""
        config = TeamcenterClientConfig(
            base_url="https://teamcenter.example/tc",
            auth_mode=AuthMode.COOKIE,
            jsessionid="secret-session",
        )

        self.assertEqual(config.auth_mode, AuthMode.COOKIE)

    def test_configuration_rejects_unbounded_retries(self):
        """External read retries remain within a bounded operational range."""
        with self.assertRaises(TeamcenterConfigurationError):
            TeamcenterClientConfig(
                base_url="https://teamcenter.example/tc",
                username="user",
                password="password",
                max_read_retries=100,
            )

    @override_settings(DEBUG=False)
    def test_production_rejects_insecure_transport(self):
        """Production cannot disable TLS or use a plain HTTP Teamcenter URL."""
        with self.assertRaises(TeamcenterConfigurationError):
            validate_transport_security("http://teamcenter.example/tc", False)


class TeamcenterTransportTests(SimpleTestCase):
    """Verify Teamcenter transport URL and CSRF behavior."""

    def test_service_url_uses_configured_root(self):
        """Service paths stay below the configured REST root."""
        transport = TeamcenterTransport(self.config(), self.session())

        url = transport.service_url("Core-2006-03-DataManagement/loadObjects")

        self.assertEqual(
            url,
            "https://teamcenter.example/tc/RestServices/Core-2006-03-DataManagement/loadObjects",
        )

    def test_sync_csrf_copies_cookie_to_header(self):
        """The XSRF cookie is mirrored into Teamcenter's request header."""
        session = self.session()
        session.cookies.set("XSRF-TOKEN", "token-value", domain="teamcenter.example", path="/")
        transport = TeamcenterTransport(self.config(), session)

        token = transport.sync_csrf_token()

        self.assertEqual(token, "token-value")
        self.assertEqual(session.headers["X-XSRF-TOKEN"], "token-value")

    def test_response_size_guard_checks_streamed_content(self):
        """Streamed responses larger than the limit are rejected before JSON parsing."""
        transport = TeamcenterTransport(self.config(), self.session())
        response = Mock(headers={}, encoding="utf-8")
        response.iter_content.return_value = [b"x" * (transport.config.max_response_bytes + 1)]

        with self.assertRaises(TeamcenterProtocolError):
            read_bounded_content(response, transport.config.max_response_bytes)

    @staticmethod
    def config() -> TeamcenterClientConfig:
        """Return valid test configuration."""
        return TeamcenterClientConfig(
            base_url="https://teamcenter.example/tc", username="user", password="password"
        )

    @staticmethod
    def session() -> Mock:
        """Return a requests-compatible mocked session."""
        session = Mock()
        session.headers = {}
        session.cookies = RequestsCookieJar()
        return session


@override_settings(
    TEAMCENTER_BASE_URL="https://teamcenter.example/tc",
    TEAMCENTER_AUTH_MODE="password",
    TEAMCENTER_USERNAME="service-user",
    TEAMCENTER_PASSWORD="service-password",
    TEAMCENTER_SERVICE_ROOT="RestServices",
    TEAMCENTER_VERIFY_SSL="true",
)
class TeamcenterApiTests(TestCase):
    """Verify authentication, validation, and API response behavior."""

    def setUp(self):
        """Create an authenticated non-administrator API client."""
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="teamcenter-user")
        self.client.force_authenticate(self.user)

    def test_status_never_returns_credentials(self):
        """Configuration status exposes readiness without secret values."""
        response = self.client.get(reverse("teamcenter_status"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["configured"])
        self.assertNotIn("username", response.data)
        self.assertNotIn("password", response.data)

    @patch("teamcenter.views.execute_with_client")
    def test_load_objects_delegates_validated_uids(self, execute_client):
        """A valid object-load request reaches the isolated client service."""
        execute_client.return_value = {"objects": []}

        response = self.client.post(
            reverse("teamcenter_load_objects"), {"uids": ["UID-1"]}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        operation = execute_client.call_args.args[0]
        fake_client = Mock()
        fake_client.load_objects.return_value = {"objects": []}
        operation(fake_client)
        fake_client.load_objects.assert_called_once_with(["UID-1"])

    def test_invalid_query_criteria_are_rejected(self):
        """Parallel query entries and values must have equal lengths."""
        payload = {"query_uid": "QUERY", "entries": ["Name"], "values": ["A", "B"]}

        response = self.client.post(reverse("teamcenter_execute_query"), payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")

    def test_property_updates_require_administrator(self):
        """A normal authenticated user cannot mutate Teamcenter properties."""
        response = self.client.patch(reverse("teamcenter_set_properties"), {}, format="json")

        self.assertEqual(response.status_code, 403)
