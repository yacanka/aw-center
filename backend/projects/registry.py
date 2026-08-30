"""Read-only technical capability catalog keyed by canonical project slug."""

from types import MappingProxyType

from .types import ProjectDefinition


GOKBEY_DCC_CONTROLLER = "gokbey_dcc"


def _definition(
    slug: str,
    jira_component: str,
    *,
    dcc_controller: str | None = None,
):
    return ProjectDefinition(
        slug=slug,
        capabilities=("dcc", "compliance", "organization"),
        jira_component=jira_component,
        dcc_label=jira_component,
        dcc_template_name=f"{slug}_dcc_template.docx",
        mail_template_name=f"{slug}_mail_template",
        dcc_controller=dcc_controller,
    )


PROJECT_DEFINITIONS = MappingProxyType(
    {
        "ozgur": _definition("ozgur", "OZGUR"),
        "piku": _definition("piku", "PIKU"),
        "aesa": _definition("aesa", "AESA"),
        "havasoj": _definition("havasoj", "HAVASOJ"),
        "hys": _definition("hys", "HYS"),
        "blok30": _definition("blok30", "BLOK30"),
        "blok4050": _definition("blok4050", "BLOK4050"),
        "gokbey": _definition(
            "gokbey",
            "GOKBEY",
            dcc_controller=GOKBEY_DCC_CONTROLLER,
        ),
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
    normalized_component = jira_component.strip().upper()
    return next(
        (
            definition
            for definition in PROJECT_DEFINITIONS.values()
            if definition.jira_component == normalized_component
        ),
        None,
    )
