"""Gokbey-specific rules for the final DCC render context."""

from types import MappingProxyType

JANDARMA_PANEL_RESPONSIBLES = MappingProxyType(
    {
        "flight": "Utku İnanç PEHLİVAN",
        "human factor": "Aslı ALPSOY",
        "electrical systems/e3": "Merve HELVACI",
    }
)


def control_gokbey_dcc(render_context):
    """Apply Gokbey-specific panel rules to the final DOCX render context."""

    panels = render_context.get("Panels", [])
    if not isinstance(panels, list):
        return render_context
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        panel_name = extract_panel_name(panel.get("Panel_Name"))
        mandatory_name = JANDARMA_PANEL_RESPONSIBLES.get(panel_name.casefold())
        if mandatory_name:
            panel["Panel_AS_Name"] = combine_names(
                mandatory_name, str(panel.get("Panel_AS_Name") or "").strip()
            )
    return render_context


def extract_panel_name(summary):
    """Extract the legacy name preceding the first standalone `Panel` marker."""

    normalized = str(summary or "").strip()
    prefix, marker, _suffix = normalized.partition("Panel")
    return prefix.strip() if marker else normalized


def combine_names(mandatory_name, current_name):
    """Prepend a mandatory person unless that person is already assigned."""

    if not current_name or comparable_name(mandatory_name) == comparable_name(current_name):
        return mandatory_name
    return f"{mandatory_name}, {current_name}"


def comparable_name(value):
    """Normalize Turkish dotted uppercase I for duplicate-name comparison."""

    return value.casefold().replace("\N{COMBINING DOT ABOVE}", "")
