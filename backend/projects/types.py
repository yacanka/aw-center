"""Shared type definitions for project metadata."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ProjectDefinition:
    """Describe a project app without exposing deployment-specific filesystem paths."""

    slug: str
    display_name: str
    app_label: str
    url_prefix: str
    enabled: bool = True
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    jira_component: Optional[str] = None
    dcc_label: Optional[str] = None
    dcc_template_name: Optional[str] = None
    mail_template_name: Optional[str] = None
    dcc_parent_path_setting: Optional[str] = None
