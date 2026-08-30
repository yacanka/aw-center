"""Classify JIRA write failures without exposing provider details."""

from jira import JIRAError

from .sessions import jira_status_code


def create_result_is_uncertain(error):
    """Return whether a failed create may already have reached JIRA."""

    if isinstance(error, JIRAError):
        status = jira_status_code(error)
        return status is None or status >= 500
    return True
