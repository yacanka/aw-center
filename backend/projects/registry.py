"""Read-only technical capability catalog keyed by canonical project slug."""

from types import MappingProxyType

from .types import ProjectDefinition


GOKBEY_DCC_CONTROLLER = "gokbey_dcc"


def _definition(slug, *, dcc_controller=None, capabilities=("jira", "compliance", "organization")):
    return ProjectDefinition(slug=slug, capabilities=capabilities, dcc_controller=dcc_controller)


PROJECT_DEFINITIONS = MappingProxyType({
    "ozgur": _definition("ozgur", dcc_controller="flight_manuals_dcc"),
    "piku": _definition("piku"),
    "aesa": _definition("aesa"),
    "havasoj": _definition("havasoj"),
    "hys": _definition("hys", dcc_controller="flight_manuals_dcc"),
    "blok30": _definition("blok30"),
    "blok4050": _definition("blok4050"),
    "gokbey": _definition("gokbey", dcc_controller=GOKBEY_DCC_CONTROLLER),
    "gokbey_jandarma": _definition("gokbey_jandarma", dcc_controller="gokbey_variant_dcc"),
    "gokbey_sivil": _definition("gokbey_sivil", dcc_controller="gokbey_variant_dcc"),
    "hurkus": _definition("hurkus", capabilities=("jira",), dcc_controller="hurkus_dcc"),
    "hurjet": _definition("hurjet"),
    **{
        slug: _definition(slug, capabilities=("compliance", "organization"))
        for slug in ("havasoj_stc1", "havasoj_stc2", "hyeu", "hurkus_aviyonik", "hjt", "hsp", "navy", "bkm", "mmu")
    },
})


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


def get_project_configuration():
    """Validate private metadata against the immutable installed capabilities."""
    from .configuration import load_project_configuration

    return load_project_configuration(
        {item.slug for item in get_project_definitions_by_capability("jira")}
    )


def get_project_integration_definition(slug):
    """Join private metadata without allowing it to alter capabilities or handlers."""
    from dataclasses import replace

    definition = get_project_definition(slug)
    if "jira" not in definition.capabilities:
        return definition
    record = get_project_configuration()["projects"][definition.slug]
    return replace(definition, **{key: value for key, value in record.items() if key != "aliases"})


def find_project_by_jira_component(jira_component: str) -> ProjectDefinition | None:
    return find_projects_by_jira_components((jira_component,))[0]


def find_projects_by_jira_components(components):
    """Resolve a batch against one validated snapshot, without a stale global cache."""
    from dataclasses import replace
    from .configuration import normalize_component

    normalized = tuple(normalize_component(value) for value in components)
    if not any(normalized):
        return tuple(None for _ in normalized)
    index = {}
    for slug, record in get_project_configuration()["projects"].items():
        definition = replace(
            PROJECT_DEFINITIONS[slug],
            **{key: value for key, value in record.items() if key != "aliases"},
        )
        for name in [record["jira_component"], *record["aliases"]]:
            index[normalize_component(name)] = definition
    return tuple(index.get(value) for value in normalized)
