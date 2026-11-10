"""Gokbey-specific rules for the final DCC render context."""

from django.core.exceptions import ImproperlyConfigured

from awcenter.private_configuration import read_private_json

REQUIRED_PANELS = frozenset({"flight", "human factor", "electrical systems/e3"})


class DccPolicyConfigurationError(ImproperlyConfigured):
    """An affected document must not render with missing mandatory signatories."""


def load_panel_responsibles():
    """Read the bounded operator-owned policy afresh for each DCC render.

    The path must be absolute and outside the checkout, including symlink targets.
    POSIX files must belong to the process user with no group/other permissions.
    Windows deployments must restrict the file and parent directory with NTFS ACLs.
    """

    try:
        policy = read_private_json("GOKBEY_DCC_POLICY_FILE")
        if not isinstance(policy, dict) or set(policy) != {"schema_version", "panel_responsibles"}:
            raise ValueError
        if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
            raise ValueError
        people = policy["panel_responsibles"]
        if not isinstance(people, dict) or set(people) != REQUIRED_PANELS:
            raise ValueError
        if any(not valid_person_name(name) for name in people.values()):
            raise ValueError
        return {panel: name.strip() for panel, name in people.items()}
    # pathlib on Python 3.11 uses RuntimeError for unresolved symlink loops.
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        raise DccPolicyConfigurationError(
            "The private Gokbey DCC signatory policy is unavailable or invalid."
        ) from None


def valid_person_name(value):
    return (
        isinstance(value, str) and 0 < len(value.strip()) <= 255
        and not any(ord(character) < 32 for character in value)
    )


def control_gokbey_dcc(render_context):
    """Apply Gokbey-specific panel rules to the final DOCX render context."""

    panel_responsibles = load_panel_responsibles()
    panels = render_context.get("Panels", [])
    if not isinstance(panels, list):
        return render_context
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        panel_name = extract_panel_name(panel.get("Panel_Name"))
        mandatory_name = panel_responsibles.get(panel_name.casefold())
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
