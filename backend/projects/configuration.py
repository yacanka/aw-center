"""Private integration metadata; technical capabilities stay in the code catalog."""

import re

from rest_framework.exceptions import APIException

from awcenter.private_configuration import PrivateConfigurationError, read_private_json


class ProjectConfigurationError(APIException):
    status_code = 503
    default_code = "PROJECT_CONFIGURATION_UNAVAILABLE"
    default_detail = "Private project configuration is unavailable or invalid."


def normalize_component(value):
    return value.strip().casefold().replace("\u0307", "")


def load_project_configuration(expected_slugs):
    try:
        value = read_private_json("PROJECT_CONFIGURATION_FILE")
        if set(value) != {"schema_version", "projects", "cover_pages"}:
            raise ValueError
        expected = set(expected_slugs)
        records = value["projects"]
        if not isinstance(records, dict) or set(records) != expected:
            raise ValueError
        _validate_records(records)
        covers = value["cover_pages"]
        if not isinstance(covers, dict) or set(covers) != {"match_text", "match_label", "default_label"}:
            raise ValueError
        if any(not _valid_text(text) for text in covers.values()):
            raise ValueError
        return value
    except (PrivateConfigurationError, ValueError, TypeError, AttributeError):
        raise ProjectConfigurationError() from None


def _validate_records(records):
    seen = set()
    fields = {"jira_component", "aliases", "dcc_label", "dcc_template_name", "mail_template_name"}
    for record in records.values():
        if not isinstance(record, dict) or set(record) != fields:
            raise ValueError
        if any(not _valid_text(record[name]) for name in fields - {"aliases"}):
            raise ValueError
        aliases = record["aliases"]
        if not isinstance(aliases, list) or len(aliases) > 20:
            raise ValueError
        for name in [record["jira_component"], *aliases]:
            if not _valid_text(name) or normalize_component(name) in seen:
                raise ValueError
            seen.add(normalize_component(name))
        template = record["dcc_template_name"]
        if any(character in template for character in "/\\:") or not template.endswith(".docx"):
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_-]+", record["mail_template_name"]):
            raise ValueError


def _valid_text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 255 and value.isprintable()
