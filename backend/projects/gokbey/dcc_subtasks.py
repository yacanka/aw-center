"""Gokbey Jandarma rules for DCC panel subtasks."""

from types import MappingProxyType

from dcc.services.subtask_control_contract import SubtaskControlResult


JANDARMA_PANEL_RESPONSIBLES = MappingProxyType(
    {
        "flight": "Utku İnanç PEHLİVAN",
        "human factor": "Aslı ALPSOY",
        "electrical systems/e3": "Merve HELVACI",
    }
)


def control_jandarma_subtasks(subtasks):
    """Add mandatory Jandarma panel responsibles without losing JIRA assignees."""

    overrides, additions = build_assignee_overrides(subtasks)
    return SubtaskControlResult(
        subtasks=subtasks,
        render_context={"mandatory_panel_responsibles": additions},
        placeholder_overrides=overrides,
    )


def build_assignee_overrides(subtasks):
    """Return standard placeholders and auditable alternative render records."""

    overrides, additions = {}, []
    for index, subtask in enumerate(subtasks, start=1):
        panel_name = extract_panel_name(read_field(subtask.fields, "summary"))
        mandatory_name = JANDARMA_PANEL_RESPONSIBLES.get(panel_name.casefold())
        if not mandatory_name:
            continue
        current_name = person_name(read_field(subtask.fields, "assignee"))
        overrides[f"Panel_AS_Name_{index}"] = combine_names(mandatory_name, current_name)
        additions.append({"panel": panel_name, "responsible": mandatory_name})
    return overrides, additions


def extract_panel_name(summary):
    """Extract the legacy name preceding the first standalone `Panel` marker."""

    normalized = str(summary or "").strip()
    prefix, marker, _suffix = normalized.partition("Panel")
    return prefix.strip() if marker else normalized


def person_name(person):
    """Format a JIRA assignee consistently with standard DCC placeholders."""

    from dcc.document_fields import display_name

    return display_name(person)


def combine_names(mandatory_name, current_name):
    """Prepend a mandatory person unless that person is already assigned."""

    if not current_name or comparable_name(mandatory_name) == comparable_name(current_name):
        return mandatory_name
    return f"{mandatory_name}, {current_name}"


def comparable_name(value):
    """Normalize Turkish dotted uppercase I for duplicate-name comparison."""

    return value.casefold().replace("\N{COMBINING DOT ABOVE}", "")


def read_field(value, name):
    """Read a field from the JIRA object or a test mapping."""

    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)
