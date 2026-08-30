"""Bounded JIRA adapter used behind the integrations boundary."""

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from django.conf import settings
from jira import JIRA, JIRAError

CERTIFICATE_FILE = settings.CERTIFICATES_DIR / "JIRA_Chain.crt"
ISSUE_KEY_PATTERN = re.compile(r"[A-Z]+-\d+")
logger = logging.getLogger(__name__)


class JiraConfigurationError(ValueError):
    """Represent an unsafe or incomplete server-side JIRA configuration."""


def ISO_time_to_string(date_str):
    """Format a JIRA timestamp using the existing DCC display contract."""

    try:
        value = datetime.fromisoformat(date_str)
    except ValueError:
        value = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S.%f")
    return f"{value.day:02}.{value.month:02}.{value.year}"


def split_text_by_chracter(text, character):
    """Return the text before a delimiter while preserving legacy behavior."""

    index = text.find(character)
    return text[:index].strip() if index != -1 else text


class JiraConnector:
    """Adapt one already-established ephemeral JIRA browser session."""

    def __init__(self, server_url, jira_session_id):
        parsed_url = validated_server_url(server_url)
        credential = validated_session_id(jira_session_id)
        certificate = str(CERTIFICATE_FILE) if CERTIFICATE_FILE.exists() else True
        options = {"server": server_url, "verify": certificate}
        try:
            self.jira = JIRA(
                options=options,
                get_server_info=False,
                timeout=10,
            )
        except JIRAError:
            logger.warning("JIRA client initialization was rejected.")
            raise
        self.jira._session.cookies.set(
            "JSESSIONID",
            credential,
            domain=parsed_url.hostname,
            path=parsed_url.path.rstrip("/") or "/",
        )
        self.issue_key = None

    def current_user(self):
        """Return the authenticated JIRA identity or propagate the upstream failure."""

        return self.jira.myself()

    def myself(self):
        """Compatibility wrapper returning no identity when JIRA rejects the session."""

        try:
            return self.current_user()
        except JIRAError:
            logger.warning("JIRA user lookup was rejected.")
            return None
        except Exception as error:
            logger.warning(
                "JIRA user lookup failed failure_type=%s",
                error.__class__.__name__,
            )
            return None

    def set_issue(self, url_or_key):
        """Resolve and store a bounded JIRA issue key."""

        match = ISSUE_KEY_PATTERN.search(str(url_or_key or ""))
        if not match:
            raise ValueError("Can not resolve issue.")
        self.issue_key = match.group(0)

    def get_issue_key(self):
        return self.issue_key

    def get_client(self):
        return self.jira

    def check_issue_key(self):
        if self.issue_key is None:
            raise ValueError("Set an issue key in JiraConnector.")

    def get_issue(self, log=False):
        self.check_issue_key()
        return self.jira.issue(self.issue_key)

    def create_issue(self, issue_dict):
        try:
            return self.jira.create_issue(fields=issue_dict)
        except JIRAError:
            logger.warning("JIRA issue creation was rejected.")
            raise

    def find_issue_by_label(self, label):
        """Return the oldest issue carrying one server-generated idempotency label."""

        query = f'labels = "{label}" ORDER BY created ASC'
        issues = self.jira.search_issues(query, maxResults=1, fields="key")
        return issues[0] if issues else None

    def find_attachment_by_filename(self, issue_key, filename):
        """Return one attachment carrying a server-generated exact filename."""

        self.set_issue(issue_key)
        issue = self.jira.issue(self.issue_key, fields="attachment")
        attachments = getattr(issue.fields, "attachment", ()) or ()
        return next(
            (
                attachment
                for attachment in attachments
                if str(getattr(attachment, "filename", "")) == str(filename)
            ),
            None,
        )

    def create_subtask(
        self,
        summary,
        description="",
        assignee=None,
        priority=None,
        duedate=None,
        due_date=None,
        extra_fields=None,
    ):
        """Create a sub-task, including the site's fallback assignee field."""

        effective_due_date = duedate if duedate is not None else due_date
        fields = self.build_subtask_fields(
            summary,
            description,
            assignee,
            effective_due_date,
            extra_fields,
        )
        if priority:
            fields["priority"] = {"name": priority}
        try:
            return self.jira.create_issue(fields=fields)
        except JIRAError as error:
            if not assignee or not self.is_default_assignee_error(error):
                logger.warning("JIRA sub-task creation was rejected.")
                raise
        fields.pop("assignee", None)
        fields["customfield_28701"] = {"name": assignee}
        try:
            return self.jira.create_issue(fields=fields)
        except JIRAError:
            logger.warning("JIRA fallback sub-task creation was rejected.")
            raise

    @staticmethod
    def is_default_assignee_error(error):
        error_text = str(error).lower()
        return (
            "assignee" in error_text
            or "field" in error_text and "screen" in error_text
            or "field" in error_text and "unknown" in error_text
        )

    def get_subtask_fields(self):
        self.check_issue_key()
        project_key = self.issue_key.split("-")[0]
        return self.get_create_fields(project_key, "Sub-task")

    def get_create_fields(self, project_key, issue_type_name):
        metadata = self.jira.createmeta(
            projectKeys=project_key,
            issuetypeNames=issue_type_name,
            expand="projects.issuetypes.fields",
        )
        projects = metadata.get("projects", [])
        issue_types = projects[0].get("issuetypes", []) if projects else []
        fields = issue_types[0].get("fields", {}) if issue_types else {}
        return [
            {
                "id": key,
                "name": value.get("name", key),
                "required": value.get("required", False),
                "hasDefaultValue": value.get("hasDefaultValue", False),
                "schema": value.get("schema", {}),
                "allowedValues": value.get("allowedValues", []),
            }
            for key, value in fields.items()
        ]

    def get_create_field_allowed_values(self, project_key, issue_type_name, field_id):
        fields = self.get_create_fields(project_key, issue_type_name)
        field = next((item for item in fields if item["id"] == field_id), None)
        return field.get("allowedValues", []) if field else []

    def build_subtask_fields(
        self,
        summary,
        description="",
        assignee=None,
        duedate=None,
        extra_fields=None,
    ):
        fields = {
            "project": self.issue_key.split("-")[0],
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Sub-task"},
            "parent": {"key": self.issue_key},
        }
        if duedate is not None:
            fields["duedate"] = self.format_due_date(duedate)
        if extra_fields:
            fields.update(
                {key: value for key, value in extra_fields.items() if value not in [None, ""]}
            )
        if assignee:
            fields["assignee"] = {"name": assignee}
        return fields

    @staticmethod
    def format_due_date(duedate):
        if isinstance(duedate, int):
            return (datetime.now() + timedelta(days=duedate)).date().isoformat()
        return duedate

    def get_open_subtask(self):
        self.check_issue_key()
        issue = self.jira.issue(self.issue_key)
        return [
            subtask
            for reference in issue.fields.subtasks
            if (subtask := self.jira.issue(reference.key)).fields.status.name != "Closed"
        ]

    def add_attachment(self, file, filename=None):
        self.check_issue_key()
        return self.jira.add_attachment(
            issue=self.issue_key,
            attachment=file,
            filename=filename,
        )


def validated_server_url(server_url):
    """Reject credential-bearing or non-production-safe JIRA URLs."""

    parsed = urlparse(str(server_url or "").strip())
    allowed_schemes = {"http", "https"} if settings.DEBUG else {"https"}
    if (
        parsed.scheme.lower() not in allowed_schemes
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise JiraConfigurationError("JIRA is not configured safely.")
    return parsed


def validated_session_id(value):
    """Require a bounded opaque credential without logging or persisting it."""

    credential = str(value or "").strip()
    if not 8 <= len(credential) <= 4096 or any(char.isspace() for char in credential):
        raise ValueError("The JIRA session credential is invalid.")
    return credential
    return credential
