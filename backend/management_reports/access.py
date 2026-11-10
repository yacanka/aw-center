"""Enabled compliance projects and live project-role authorization for reports."""

from rest_framework.exceptions import PermissionDenied, ValidationError

from orgs.access_policy import authorized_project_ids
from orgs.models import Project, ProjectRoleAssignment
from projects.registry import get_project_definitions_by_capability


def reporting_projects():
    """Resolve technical capabilities to business-owned names and enabled state."""
    slugs = [item.slug for item in get_project_definitions_by_capability("compliance")]
    return Project.objects.filter(enabled=True, slug__in=slugs)


def visible_projects(user):
    return reporting_projects().filter(pk__in=authorized_project_ids(
        user, ProjectRoleAssignment.Domain.COMPLIANCE, ProjectRoleAssignment.Role.VIEWER,
    ))


def project_options(user):
    return [{"slug": item.slug, "display_name": item.name} for item in visible_projects(user)]


def authorized_projects(user, slugs):
    """Require a unique enabled scope and current access to every project."""
    projects = {item.slug: item for item in reporting_projects()}
    if not slugs or len(slugs) > len(projects) or len(set(slugs)) != len(slugs):
        raise ValidationError({"project_slugs": "Choose a nonempty, unique enabled project scope."})
    if any(slug not in projects for slug in slugs):
        raise ValidationError({"project_slugs": "Unknown or disabled reporting project."})
    visible = set(visible_projects(user).values_list("slug", flat=True))
    if not set(slugs).issubset(visible):
        raise PermissionDenied("Project view permission is required for every selected project.")
    return [projects[slug] for slug in sorted(slugs)]
