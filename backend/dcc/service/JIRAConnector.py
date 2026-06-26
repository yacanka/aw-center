from jira import JIRA, JIRAError
from typing import Dict, Any
import pprint
import re
from docxtpl import DocxTemplate
from datetime import datetime, timedelta
import os
from urllib.parse import urlparse
from django.conf import settings

CERTIFICATE_FILE = settings.CERTIFICATES_DIR / "JIRA_Chain.crt"

def ISO_time_to_string(date_str):
    try:
        dt = datetime.fromisoformat(date_str) 
    except ValueError:
        dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f') 
    return f"{dt.day:02}.{dt.month:02}.{dt.year}"
    

def split_text_by_chracter(text, character):
    index = text.find(character)
    if index != -1:
        return (text[:index]).strip()
    return text

def parseJiraError(e):
    if hasattr(e, "response"):
        if len(e.response.text) < 100:
            return e.response.text
        else:
            return e.response.reason
    else:
        return e.text

class JiraConnector:
    def __init__(self, server_url: str, username = None, password = None, jira_session_id=None) -> None:
        
        cert_path = CERTIFICATE_FILE if CERTIFICATE_FILE.exists() else False
        options = {"server": server_url, "verify": cert_path}
        try:
            if jira_session_id:
                self.jira = JIRA(options=options, get_server_info=False, timeout=10)
                self.jira._session.cookies.set("JSESSIONID", jira_session_id, domain=urlparse(server_url).hostname, path=urlparse(server_url).path)
            else:
                self.jira = JIRA(options=options, basic_auth=(username, password))
        except JIRAError as e:
            self.jira = None
            print(f"Error while connecting JIRA server: {parseJiraError(e)}")
            raise
        
    def check_issue_key(self):
        if self.issue_key is None:
            raise ValueError("Set a issue key in JIRAConnector")

    def set_issue(self, url_or_key):
        try:
            pattern = r'[A-Z]+-\d+'
            match = re.search(pattern, url_or_key)
            if match:
                self.issue_key = match.group(0)
            else:
                raise ValueError("Can not resolve issue.")
        except ValueError as e:
            print(e)
            raise

    def get_issue_key(self):
        return self.issue_key

    def get_client(self):
        return self.jira

    def get_issue(self, log=False):
        try:
            self.check_issue_key()
            return self.jira.issue(self.issue_key)
        except ValueError as e:
            print(e)
        except JIRAError as e:
            print(f"Error while getting issue: {parseJiraError(e)}")
            raise

    def create_issue(self, issue_dict):
        try:
            created_issue = self.jira.create_issue(fields=issue_dict)
            return created_issue
        except JIRAError as e:
            print(f"Error while creating issue: {parseJiraError(e)}")
            raise

    def create_subtask(self, summary, description="", assignee=None, priority=None, duedate=None, extra_fields=None):
        """Create a JIRA sub-task with optional dynamic field values."""
        fields = self.build_subtask_fields(summary, description, assignee, duedate, extra_fields)
        if priority:
            fields['priority'] = {'name': priority}
        try:
            return self.jira.create_issue(fields=fields)
        except JIRAError as e:
            if not assignee or not self.is_default_assignee_error(e):
                print(f"Error while creating Sub-task: {parseJiraError(e)}")
                raise
        fields.pop('assignee', None)
        fields['customfield_28701'] = {'name': assignee}
        try:
            return self.jira.create_issue(fields=fields)
        except JIRAError as e:
            print(f"Error while creating Sub-task with custom field: {parseJiraError(e)}")
            raise

    def is_default_assignee_error(self, error):
        """Return whether JIRA rejected the default assignee field placement."""
        error_text = str(error).lower()
        return (
            'assignee' in error_text
            or 'field' in error_text and 'screen' in error_text
            or 'field' in error_text and 'unknown' in error_text
        )


    def get_subtask_fields(self):
        """Return createmeta field descriptors for the current issue project sub-task type."""
        self.check_issue_key()
        project_key = self.issue_key.split('-')[0]
        metadata = self.jira.createmeta(
            projectKeys=project_key,
            issuetypeNames='Sub-task',
            expand='projects.issuetypes.fields'
        )
        projects = metadata.get('projects', [])
        issue_types = projects[0].get('issuetypes', []) if projects else []
        fields = issue_types[0].get('fields', {}) if issue_types else {}
        return [self.build_subtask_field_descriptor(key, value) for key, value in fields.items()]

    def build_subtask_field_descriptor(self, field_identifier, metadata):
        """Build frontend-safe field metadata from JIRA createmeta."""
        descriptor = {
            'id': field_identifier,
            'name': metadata.get('name', field_identifier),
            'required': metadata.get('required', False),
            'schema': metadata.get('schema', {}),
            'allowedValues': metadata.get('allowedValues', []),
        }
        configured_input_type = self.get_configured_subtask_input_type(field_identifier)
        if configured_input_type:
            descriptor['inputType'] = configured_input_type
        return descriptor

    def get_configured_subtask_input_type(self, field_identifier):
        """Return the configured editor type for a JIRA sub-task field."""
        input_types = getattr(settings, 'JIRA_SUBTASK_FIELD_INPUT_TYPES', {})
        configured_type = input_types.get(field_identifier)
        allowed_types = {'date', 'number', 'person', 'text'}
        return configured_type if configured_type in allowed_types else None

    def build_subtask_fields(self, summary, description='', assignee=None, duedate=None, extra_fields=None):
        """Build the fields payload used by JIRA create_issue for sub-tasks."""
        fields = {
            'project': self.issue_key.split('-')[0],
            'summary': summary,
            'description': description,
            'issuetype': {'name': 'Sub-task'},
            'parent': {'key': self.issue_key}
        }
        if duedate is not None:
            fields['duedate'] = self.format_due_date(duedate)
        if extra_fields:
            fields.update({key: value for key, value in extra_fields.items() if value not in [None, '']})
        if assignee:
            fields['assignee'] = {'name': assignee}
        return fields

    def format_due_date(self, duedate):
        """Format an integer day offset or pass through an explicit JIRA due date value."""
        if isinstance(duedate, int):
            return (datetime.now() + timedelta(days=duedate)).date().isoformat()
        return duedate

    def update_issue(self: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.check_issue_key()
            updated_issue = self.jira.update_issue(self.issue_key, fields=fields)
            return updated_issue.fields
        except ValueError as e:
            print(e)
        except JIRAError as e:
            print(f"Error while updating issue: {parseJiraError(e)}")
            raise
    
    def explore_issue_fields(self, none_filter=True):
        try:
            self.check_issue_key()
            issue = self.jira.issue(self.issue_key)
            fields = issue.raw.get('fields', {})
            print(f"--- Issue {self.issue_key} ---\n")
            for field_name, value in fields.items():
                if none_filter and value == None:
                    continue
                print(f"Field: {field_name}")
                pprint.pprint(value)
                print("-" * 30)
        except ValueError as e:
            print(e)
        except JIRAError as e:
            print(f"Error while exploring issue: {parseJiraError(e)}")
            raise

    def get_open_subtask(self):
        try:
            self.check_issue_key()
            
            issue = self.jira.issue(self.issue_key)
            subtask_list = []
            for subtask in issue.fields.subtasks:
                subtaskElement = self.jira.issue(subtask.key)
                if subtaskElement.fields.status.name != "Closed":
                    subtask_list.append(subtaskElement)

            return subtask_list
        except ValueError as e:
            print(e)
        except JIRAError as e:
            print(f"Error while getting subtasks: {parseJiraError(e)}")
            raise

    def add_attachment(self, file, filename=None):
        try:
            self.check_issue_key()
            attachment = self.jira.add_attachment(issue=self.issue_key, attachment=file, filename=filename)
            return attachment
        except ValueError as e:
            print(e)
        except JIRAError as e:
            print(f"Error while adding attachment: {parseJiraError(e)}")
            raise

    def save_attachment(self, save_path):
        try:
            self.check_issue_key()
            issue = self.jira.issue(self.issue_key)
            for attachment in issue.fields.attachment:
                filename = attachment.filename
                content = attachment.get()

                with open(filename, "wb") as f:
                    f.write(content)
                    print(f"{filename} saved!")
        except ValueError as e:
            print(e)
        except JIRAError as e:
            print(f"Error while getting attachment: {parseJiraError(e)}")
            raise

    def myself(self):
        try:
            return self.jira.myself()
        except JIRAError as e:
            print(f"Error while getting user info: {e.response.reason}")
            return None
        except Exception as e:
            print(e.text())
            return None