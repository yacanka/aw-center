"""Private integration metadata; technical capabilities stay in the code catalog."""

from collections import Counter
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
    value = _read_configuration()
    value["projects"] = {
        slug: fields for slug, record in value["projects"].items()
        if slug in expected_slugs and (fields := _project_fields(record))
    }
    return value


def _read_configuration():
    try:
        value = read_private_json("PROJECT_CONFIGURATION_FILE")
        if set(value) != {"schema_version", "projects", "cover_pages"}:
            raise ValueError
        if not isinstance(value["projects"], dict):
            raise ValueError
        covers = value["cover_pages"]
        if not isinstance(covers, dict) or set(covers) != {"match_text", "match_label", "default_label"}:
            raise ValueError
        if any(not _valid_text(text) for text in covers.values()):
            raise ValueError
        return value
    except (PrivateConfigurationError, ValueError, TypeError, AttributeError):
        raise ProjectConfigurationError() from None


def _project_fields(record):
    """Keep only usable integration metadata for this project."""
    if not isinstance(record, dict):
        return {}
    fields = {}
    component = record.get("jira_component")
    if _valid_text(component) and normalize_component(component):
        fields["jira_component"] = component
    aliases = record.get("aliases")
    if isinstance(aliases, list) and len(aliases) <= 20:
        names = [name for name in aliases if _valid_text(name) and normalize_component(name)]
        if names:
            fields["aliases"] = names
    label = record.get("dcc_label")
    if _valid_text(label):
        fields["dcc_label"] = label
    template = record.get("dcc_template_name")
    if _valid_text(template) and template.endswith(".docx") and not any(c in template for c in "/\\:"):
        fields["dcc_template_name"] = template
    mail = record.get("mail_template_name")
    if _valid_text(mail) and re.fullmatch(r"[A-Za-z0-9_-]+", mail):
        fields["mail_template_name"] = mail
    return fields


def _valid_text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 255 and value.isprintable()

PROJECT_FIELDS = ("jira_component", "aliases", "dcc_label", "dcc_template_name", "mail_template_name")


def inspect_project_fields(slugs, *, include_values):
    """Inspect one private snapshot and disclose only validated, allowlisted values."""
    try:
        records = _read_configuration()["projects"]
    except ProjectConfigurationError:
        return {slug: {key: {"status": "unavailable"} for key in PROJECT_FIELDS} for slug in slugs}

    valid = {slug: _project_fields(records.get(slug)) for slug in slugs}
    owners = Counter()
    for fields in valid.values():
        names = [fields.get("jira_component", ""), *fields.get("aliases", [])]
        owners.update({normalize_component(name) for name in names if name})

    result = {}
    for slug, fields in valid.items():
        raw = records.get(slug, {})
        details = {}
        for key in PROJECT_FIELDS:
            value = fields.get(key)
            details[key] = {"status": _field_status(key, value, raw, owners)}
            if include_values and value is not None:
                details[key]["value"] = value
        result[slug] = details
    return result


def _field_status(key, value, raw, owners):
    if value is None:
        if not isinstance(raw, dict):
            return "invalid"
        if key not in raw or (key == "aliases" and raw[key] == []):
            return "missing"
        return "invalid"
    if key in ("jira_component", "aliases"):
        names = value if key == "aliases" else [value]
        if any(owners[normalize_component(name)] > 1 for name in names):
            return "ambiguous"
    if key == "aliases" and value != raw[key]:
        return "partial"
    return "configured"
