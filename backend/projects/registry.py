"""Read-only technical capability catalog keyed by canonical project slug."""

from types import MappingProxyType

from .types import ProjectDefinition


GOKBEY_DCC_CONTROLLER = "gokbey_dcc"


def _definition(
    slug: str,
    jira_component: str,
    *,
    dcc_controller: str | None = None,
    dcc_label: str | None = None,
    template: str | None = None,
    capabilities: tuple[str, ...] = ("dcc", "compliance", "organization"),
):
    return ProjectDefinition(
        slug=slug,
        capabilities=capabilities,
        jira_component=jira_component,
        dcc_label=dcc_label or jira_component,
        dcc_template_name=template or f"{slug}_dcc_template.docx",
        mail_template_name=f"{slug}_mail_template",
        dcc_controller=dcc_controller,
    )


PROJECT_DEFINITIONS = MappingProxyType(
    {
        "ozgur": _definition("ozgur", "Özgür", dcc_controller="flight_manuals_dcc"),
        "piku": _definition("piku", "Piku"),
        "aesa": _definition("aesa", "AESA"),
        "havasoj": _definition("havasoj", "HAVASOJ"),
        "hys": _definition("hys", "HYS", dcc_controller="flight_manuals_dcc"),
        "blok30": _definition("blok30", "BLOK30"),
        "blok4050": _definition("blok4050", "BLOK4050"),
        "gokbey": _definition(
            "gokbey",
            "GOKBEY",
            dcc_controller=GOKBEY_DCC_CONTROLLER,
        ),
        "gokbey_jandarma": _definition(
            "gokbey_jandarma", "Gökbey Jandarma", dcc_label="GJ",
            template="gj_dcc_template.docx", dcc_controller="gokbey_variant_dcc",
        ),
        "gokbey_sivil": _definition(
            "gokbey_sivil", "Gökbey Sivil", dcc_label="T625",
            template="t625_dcc_template.docx", dcc_controller="gokbey_variant_dcc",
        ),
        "hurkus": _definition(
            "hurkus", "HÜRKUŞ 2", dcc_label="HK", template="hk_dcc_template.docx",
            capabilities=("dcc",), dcc_controller="hurkus_dcc",
        ),
        "hurjet": _definition("hurjet", "HURJET"),
    }
)


class UnknownProjectDefinitionError(LookupError):
    """Raised when a required technical project definition is absent."""


def get_project_definition(slug: str) -> ProjectDefinition:
    normalized_slug = slug.strip().lower()
    definition = PROJECT_DEFINITIONS.get(normalized_slug)
    if definition is None:
        raise UnknownProjectDefinitionError(f"Unknown project slug: {slug!r}")
    return definition


def get_project_definitions_by_capability(capability: str) -> tuple[ProjectDefinition, ...]:
    normalized_capability = capability.strip().lower()
    return tuple(
        definition
        for definition in PROJECT_DEFINITIONS.values()
        if normalized_capability in definition.capabilities
    )


def find_project_by_jira_component(jira_component: str) -> ProjectDefinition | None:
    normalized_component = jira_component.strip().casefold().replace("\u0307", "")
    # Preserve the historical ASCII JIRA component while accepting its corrected name.
    if normalized_component == "ozgur":
        return PROJECT_DEFINITIONS["ozgur"]
    return next(
        (
            definition
            for definition in PROJECT_DEFINITIONS.values()
            if (definition.jira_component or "").casefold().replace("\u0307", "") == normalized_component
        ),
        None,
    )
