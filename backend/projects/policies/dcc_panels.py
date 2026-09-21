"""Small project rules over the isolated, canonical DCC render context."""

from django.conf import settings

from .gokbey import extract_panel_name


def control_flight_manuals(context):
    """Expose flight-manual and ICA signatories for HYS and Özgür templates."""

    for panel in context.get("Panels", []):
        name = extract_panel_name(panel.get("Panel_Name")).casefold()
        prefix = "flight_manuals" if "flight" in name else "ica" if "ica" in name else None
        if prefix:
            context[f"{prefix}_as_name"] = panel.get("as_name", panel.get("Panel_AS_Name", ""))
            context[f"{prefix}_update_time"] = panel.get("Panel_Updated_Time", "")
    return context


def control_gokbey_variant(context):
    """Move dedicated assessments out of the general Gökbey variant panel table."""

    regular_panels = []
    for panel in context.get("Panels", []):
        name = extract_panel_name(panel.get("Panel_Name")).casefold()
        software_assignee = settings.GOKBEY_SOFTWARE_AS_NAME.strip()
        if "software" in name and software_assignee:
            panel["as_name"] = software_assignee
            panel["Panel_AS_Name"] = software_assignee
        prefixes = [prefix for prefix in ("rfm", "protection", "osd") if prefix in name]
        if not prefixes:
            regular_panels.append(panel)
        for prefix in prefixes:
            append_dedicated_assessment(context, prefix, panel)
    context["Panels"] = regular_panels
    return context


def append_dedicated_assessment(context, prefix, panel):
    """Keep all distinct assessment values when several subtasks share a section."""

    assignee = panel.get("as_name", panel.get("Panel_AS_Name", ""))
    if prefix == "protection":
        assignee = joined_values(assignee, panel.get("candidate_as_name", ""), ", ")
    values = {
        "as_name": assignee,
        "update_time": panel.get("Panel_Updated_Time", ""),
        "affected_requirements": panel.get("Affected_Requirements", ""),
        "further_compliance": panel.get("Further_Compliance", ""),
        "design_change_assessment": panel.get("Design_Change_Assessment", ""),
    }
    for suffix, value in values.items():
        key = f"{prefix}_{suffix}"
        separator = ", " if suffix == "as_name" else "\n"
        context[key] = joined_values(context.get(key, ""), value, separator)


def joined_values(current, value, separator):
    if not value or value == current:
        return current
    return separator.join(item for item in (current, value) if item)
