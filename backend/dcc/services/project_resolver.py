"""Resolve DCC project definitions from JIRA issue metadata."""

from collections.abc import Iterable
from typing import Any

from projects.registry import find_project_by_jira_component
from projects.types import ProjectDefinition

DCC_CAPABILITY = "dcc"


class DccProjectResolutionError(LookupError):
    """Base error for controlled DCC project resolution failures."""


class UnknownDccProjectComponentError(DccProjectResolutionError):
    """Raised when no JIRA component maps to a registered project."""


class DccCapabilityMissingError(DccProjectResolutionError):
    """Raised when a resolved project cannot be used by DCC workflows."""


def resolve_project_from_jira_components(components: Iterable[Any]) -> ProjectDefinition:
    """Return the first DCC-capable project definition matching JIRA components."""

    return resolve_projects_from_jira_components(components)[0]


def resolve_projects_from_jira_components(
    components: Iterable[Any],
) -> tuple[ProjectDefinition, ...]:
    """Return every distinct DCC-capable project represented by JIRA components."""

    component_names = tuple(_extract_component_names(components))
    projects = []
    seen_slugs = set()
    for component_name in component_names:
        project_definition = find_project_by_jira_component(component_name)
        if project_definition is None:
            continue
        if DCC_CAPABILITY not in project_definition.capabilities:
            raise DccCapabilityMissingError(
                f"Project {project_definition.slug!r} does not support DCC workflows."
            )
        if project_definition.slug not in seen_slugs:
            seen_slugs.add(project_definition.slug)
            projects.append(project_definition)
    if projects:
        return tuple(projects)
    raise UnknownDccProjectComponentError(
        f"No DCC project is registered for JIRA components: {component_names!r}"
    )


def _extract_component_names(components: Iterable[Any]) -> tuple[str, ...]:
    """Return non-empty component names from supported JIRA component shapes."""
    names = []
    for component in components or ():
        component_name = _extract_component_name(component)
        if component_name:
            names.append(component_name)
    return tuple(names)


def _extract_component_name(component: Any) -> str:
    if isinstance(component, str):
        return component.strip()
    if isinstance(component, dict):
        return str(component.get("name", "")).strip()
    return str(getattr(component, "name", "")).strip()
