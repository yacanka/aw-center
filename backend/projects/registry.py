"""Central read-only registry for AW Center project applications."""

from types import MappingProxyType

from .types import ProjectDefinition

PROJECT_DEFINITIONS = MappingProxyType(
    {
        "ozgur": ProjectDefinition(
            slug="ozgur",
            display_name="Ozgur",
            app_label="projects.ozgur",
            url_prefix="ozgur",
            enabled=True,
            capabilities=("dcc", "compdocs", "orgs"),
            tags=("active", "certification", "jira"),
            jira_component="OZGUR",
            dcc_label="Ozgur DCC",
            dcc_template_name="ozgur_dcc_template",
            mail_template_name="ozgur_mail_template",
        ),
        "piku": ProjectDefinition(
            slug="piku",
            display_name="Piku",
            app_label="projects.piku",
            url_prefix="piku",
            enabled=True,
            capabilities=("dcc", "compdocs", "orgs"),
            tags=("active", "certification", "jira"),
            jira_component="PIKU",
            dcc_label="Piku DCC",
            dcc_template_name="piku_dcc_template",
            mail_template_name="piku_mail_template",
        ),
        "aesa": ProjectDefinition(
            slug="aesa",
            display_name="AESA",
            app_label="projects.aesa",
            url_prefix="aesa",
            enabled=True,
            capabilities=("dcc", "compdocs", "orgs"),
            tags=("active", "certification", "jira"),
            jira_component="AESA",
            dcc_label="AESA DCC",
            dcc_template_name="aesa_dcc_template",
            mail_template_name="aesa_mail_template",
        ),
        "havasoj": ProjectDefinition(
            slug="havasoj",
            display_name="Havasoj",
            app_label="projects.havasoj",
            url_prefix="havasoj",
            enabled=True,
            capabilities=("dcc", "compdocs", "orgs"),
            tags=("active", "certification", "jira"),
            jira_component="HAVASOJ",
            dcc_label="Havasoj DCC",
            dcc_template_name="havasoj_dcc_template",
            mail_template_name="havasoj_mail_template",
        ),
        "hys": ProjectDefinition(
            slug="hys",
            display_name="HYS",
            app_label="projects.hys",
            url_prefix="hys",
            enabled=True,
            capabilities=("dcc", "compdocs", "orgs"),
            tags=("active", "certification", "jira"),
            jira_component="HYS",
            dcc_label="HYS DCC",
            dcc_template_name="hys_dcc_template",
            mail_template_name="hys_mail_template",
        ),
        "blok30": ProjectDefinition(
            slug="blok30",
            display_name="Blok 30",
            app_label="projects.blok30",
            url_prefix="blok30",
            enabled=True,
            capabilities=("dcc", "compdocs", "orgs"),
            tags=("active", "certification", "jira"),
            jira_component="BLOK30",
            dcc_label="Blok 30 DCC",
            dcc_template_name="blok30_dcc_template",
            mail_template_name="blok30_mail_template",
        ),
        "blok4050": ProjectDefinition(
            slug="blok4050",
            display_name="Blok 40/50",
            app_label="projects.blok4050",
            url_prefix="blok4050",
            enabled=False,
            capabilities=("dcc", "compdocs", "orgs"),
            tags=("inactive", "certification", "jira"),
            jira_component="BLOK4050",
            dcc_label="Blok 40/50 DCC",
            dcc_template_name="blok4050_dcc_template",
            mail_template_name="blok4050_mail_template",
        ),
        "gokbey": ProjectDefinition(
            slug="gokbey",
            display_name="Gokbey",
            app_label="projects.gokbey",
            url_prefix="gokbey",
            enabled=False,
            capabilities=("dcc", "compdocs", "orgs"),
            tags=("inactive", "certification", "jira"),
            jira_component="GOKBEY",
            dcc_label="Gokbey DCC",
            dcc_template_name="gokbey_dcc_template",
            mail_template_name="gokbey_mail_template",
        ),
    }
)


class UnknownProjectDefinitionError(LookupError):
    """Raised when a required project slug is not registered."""


def get_project_definition(slug: str) -> ProjectDefinition:
    """Return a project definition by slug or raise UnknownProjectDefinitionError."""
    normalized_slug = slug.strip().lower()
    definition = PROJECT_DEFINITIONS.get(normalized_slug)
    if definition is None:
        raise UnknownProjectDefinitionError(f"Unknown project slug: {slug!r}")
    return definition


def get_enabled_project_definitions() -> tuple[ProjectDefinition, ...]:
    """Return enabled project definitions in registry declaration order."""
    return tuple(definition for definition in PROJECT_DEFINITIONS.values() if definition.enabled)


def get_project_definitions_by_capability(capability: str) -> tuple[ProjectDefinition, ...]:
    """Return enabled project definitions that declare the requested capability."""
    normalized_capability = capability.strip().lower()
    return tuple(
        definition
        for definition in get_enabled_project_definitions()
        if normalized_capability in definition.capabilities
    )


def find_project_by_jira_component(jira_component: str) -> ProjectDefinition | None:
    """Return an enabled project for a JIRA component, or None when unknown."""
    normalized_component = jira_component.strip().upper()
    return next(
        (
            definition
            for definition in get_enabled_project_definitions()
            if definition.jira_component == normalized_component
        ),
        None,
    )
