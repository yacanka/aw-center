"""Build bounded, template-ready fields for DCC documents."""

from collections.abc import Iterable

from bs4 import BeautifulSoup

from .service.JIRAConnector import ISO_time_to_string, split_text_by_chracter
from .service.text_parsing import extract_text_from_text, make_surname_upper


def main_issue_fields(fields):
    """Return the stable DCC placeholders sourced from a parent JIRA issue."""

    placeholders = {}
    add_text(placeholders, "Design_Change_Title", field(fields, "summary"))
    add_text(placeholders, "DCC_Form_Number", field(fields, "customfield_45002"))
    add_text(placeholders, "Design_Change_Number", field(fields, "customfield_45000"))
    add_text(placeholders, "Design_Change_Revision", field(fields, "customfield_45001"))
    add_text(placeholders, "Design_Change_Classification", option(fields, "customfield_13716"))
    add_multiselect(placeholders, "Applicability", field(fields, "customfield_34115"))
    if field(fields, "updated"):
        placeholders["Update_Time"] = ISO_time_to_string(field(fields, "updated"))
    add_design_change_name(placeholders)
    return placeholders


def panel_fields(fields, index, parse_legacy_comment=False):
    """Return one panel subtask's template placeholders and classification data."""

    number = index + 1
    placeholders = {}
    add_text(placeholders, f"Panel_Status_{number}", field(field(fields, "status"), "name"))
    if field(fields, "updated"):
        placeholders[f"Panel_Updated_Time_{number}"] = ISO_time_to_string(field(fields, "updated"))
    assignee = field(fields, "assignee")
    placeholders[f"Panel_AS_Name_{number}"] = display_name(assignee)
    add_optional_panel_fields(placeholders, fields, number)
    append_candidate_assignee(placeholders, fields, number)
    classification = option(fields, "customfield_45004") or "Minor-No Effect"
    if parse_legacy_comment:
        classification = apply_legacy_comment(placeholders, fields, number) or classification
    return placeholders, (classification, assignee), text(field(fields, "customfield_45005"))


def add_optional_panel_fields(placeholders, fields, number):
    """Copy optional panel assessment fields without manufacturing empty values."""

    mappings = {
        "Affected_Requirements": "customfield_45006",
        "Further_Compliance": "customfield_45007",
        "Design_Change_Assessment": "customfield_45008",
    }
    for placeholder, source in mappings.items():
        add_text(placeholders, f"{placeholder}_{number}", field(fields, source))


def apply_legacy_comment(placeholders, fields, number):
    """Parse the legacy Gokbey HTML comment fields when they are available."""

    comments = field(field(fields, "comment"), "comments") or []
    if not comments:
        return ""
    content = BeautifulSoup(text(field(comments[0], "body")), "html.parser").get_text(" ", strip=True)
    values = legacy_comment_values(content)
    for key, value in values.items():
        add_text(placeholders, f"{key}_{number}", value)
    return values["Certification_Change_Classification"]


def legacy_comment_values(content):
    """Extract the four structured values from the historic Gokbey comment format."""

    return {
        "Certification_Change_Classification": extract_text_from_text(
            content, "(According to GM 21.A.91): ", " Affected Requirements"
        ),
        "Affected_Requirements": extract_text_from_text(
            content, "Compliance Documents: ", " Further Compliance Study for Design Change:"
        ),
        "Further_Compliance": extract_text_from_text(
            content, " Further Compliance Study for Design Change: ", " Design Change Assessment:"
        ),
        "Design_Change_Assessment": extract_text_from_text(
            content, " Design Change Assessment: "
        ),
    }


def append_candidate_assignee(placeholders, fields, number):
    """Append a candidate assignee to the primary panel assignee display."""

    candidate = display_name(field(fields, "customfield_45421"))
    if not candidate:
        return
    key = f"Panel_AS_Name_{number}"
    placeholders[key] = ", ".join(value for value in (placeholders.get(key), candidate) if value)


def add_design_change_name(placeholders):
    """Create the legacy number/revision composite when both values exist."""

    number = placeholders.get("Design_Change_Number")
    revision = placeholders.get("Design_Change_Revision")
    if number and revision:
        placeholders["Design_Change_Name"] = f"{number} / {revision}"


def add_multiselect(placeholders, key, values):
    """Store a JIRA multiselect as a comma-separated display value."""

    iterable = values if isinstance(values, Iterable) and not isinstance(values, (str, bytes, dict)) else [values]
    normalized = [option_value(value) for value in iterable if value is not None]
    add_text(placeholders, key, ", ".join(value for value in normalized if value))


def add_text(placeholders, key, value):
    """Store a non-empty string placeholder."""

    normalized = text(value)
    if normalized:
        placeholders[key] = normalized


def option(fields, name):
    """Return a JIRA option field's display value."""

    return option_value(field(fields, name))


def option_value(value):
    """Return a display value from a JIRA option object or mapping."""

    if isinstance(value, dict):
        return text(value.get("value"))
    if isinstance(value, str):
        return text(value)
    return text(field(value, "value"))


def display_name(person):
    """Return the legacy formatted display name for a JIRA person."""

    raw_name = text(field(person, "displayName"))
    return make_surname_upper(split_text_by_chracter(raw_name, "(")) if raw_name else ""


def field(value, name):
    """Read one field from either an object or mapping without raising."""

    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def text(value):
    """Convert a scalar value to a stripped string without leaking object reprs."""

    return value.strip() if isinstance(value, str) else "" if value is None else str(value).strip()
