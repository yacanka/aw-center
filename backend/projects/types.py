"""Technical project capability definitions used by integration adapters."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProjectDefinition:
    """Technical metadata only; business name/enabled state live in orgs.Project."""

    slug: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    jira_component: str | None = None
    dcc_label: str | None = None
    dcc_template_name: str | None = None
    mail_template_name: str | None = None
    dcc_parent_path_setting: str | None = None
    dcc_controller: str | None = None
