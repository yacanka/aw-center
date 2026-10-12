"""Owner-scoped saved JIRA lists with explicit stale-write fencing."""

import json

from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from awcenter.database_errors import ContentConflict, retry_content_write
from .user_content_models import JiraUserContent


MAX_SAVED_LISTS = 50
MAX_LIST_ROWS = 100
MAX_LIST_FIELDS = 100
MAX_SAVED_BYTES = 1024 * 1024


def validate_saved_lists(value):
    if not isinstance(value, list) or len(value) > MAX_SAVED_LISTS:
        raise ValidationError({"lists": "Save at most 50 lists."})
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("title"), str):
            raise ValidationError({"lists": "Each saved list requires a title."})
        rows, fields = item.get("list"), item.get("fields", [])
        if not isinstance(rows, list) or len(rows) > MAX_LIST_ROWS or any(not isinstance(row, dict) for row in rows):
            raise ValidationError({"lists": "Each list supports at most 100 object rows."})
        if not isinstance(fields, list) or len(fields) > MAX_LIST_FIELDS or any(
            not isinstance(field, dict) or not isinstance(field.get("id"), str) or not isinstance(field.get("name"), str)
            for field in fields
        ):
            raise ValidationError({"lists": "Each list supports at most 100 field definitions with IDs and names."})
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ValidationError({"lists": "Provide valid JSON content."}) from error
    if len(encoded) > MAX_SAVED_BYTES:
        raise ValidationError({"lists": "Saved lists must not exceed 1 MiB."})
    return value


def get_saved_lists(user):
    content = JiraUserContent.objects.filter(user=user).first()
    return {"lists": content.subtask_lists, "version": content.version} if content else {"lists": [], "version": 0}


def replace_saved_lists(user, lists, *, version):
    lists = validate_saved_lists(lists)

    def write():
        content, _ = JiraUserContent.objects.get_or_create(user=user)
        changed = JiraUserContent.objects.filter(pk=content.pk, version=version).update(
            subtask_lists=lists, version=F("version") + 1, updated_at=timezone.now())
        if not changed:
            raise ContentConflict("JIRA_CONTENT_VERSION_CONFLICT")
        return {"lists": lists, "version": version + 1}

    return retry_content_write(write, conflict_code="JIRA_CONTENT_VERSION_CONFLICT")
