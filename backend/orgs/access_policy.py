"""Single decision point for project-scoped domain authorization."""

from collections.abc import Iterable

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from .models import Project, ProjectRoleAssignment


ROLE_ORDER = {
    ProjectRoleAssignment.Domain.COMPLIANCE: ("viewer", "editor", "manager"),
    ProjectRoleAssignment.Domain.ORGANIZATION: ("viewer", "manager"),
    ProjectRoleAssignment.Domain.DCC: ("viewer", "operator", "publisher"),
}


def role_rank(domain: str, role: str | None) -> int:
    """Return a comparable rank, or -1 for an absent/invalid role."""

    try:
        return ROLE_ORDER[domain].index(role)
    except (KeyError, ValueError):
        return -1


def effective_role(user, project: Project, domain: str) -> str | None:
    """Resolve the strongest direct or group role for a project domain."""

    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return ROLE_ORDER[domain][-1]

    assignments = ProjectRoleAssignment.objects.filter(
        project=project,
        domain=domain,
    ).filter(Q(user=user) | Q(group__user=user))
    roles = assignments.values_list("role", flat=True).distinct()
    return max(roles, key=lambda item: role_rank(domain, item), default=None)


def has_project_role(user, project: Project, domain: str, minimum_role: str) -> bool:
    """Return whether a user meets the minimum role in one project/domain."""

    return role_rank(domain, effective_role(user, project, domain)) >= role_rank(
        domain,
        minimum_role,
    )


def has_role_for_all_projects(
    user,
    projects: Iterable[Project],
    domain: str,
    minimum_role: str,
) -> bool:
    """Require a role on every associated project to prevent cross-project leaks."""

    project_list = list(projects)
    return bool(project_list) and all(
        has_project_role(user, project, domain, minimum_role)
        for project in project_list
    )


def authorized_project_ids(user, domain: str, minimum_role: str):
    """Return enabled project IDs for which ``user`` meets one domain role."""

    enabled_projects = Project.objects.filter(enabled=True)
    if not user or not user.is_authenticated:
        return enabled_projects.none().values_list("pk", flat=True)
    if user.is_superuser:
        return enabled_projects.values_list("pk", flat=True)

    minimum_rank = role_rank(domain, minimum_role)
    accepted_roles = ROLE_ORDER.get(domain, ())[minimum_rank:]
    if minimum_rank < 0 or not accepted_roles:
        return enabled_projects.none().values_list("pk", flat=True)
    return (
        ProjectRoleAssignment.objects.filter(
            project__enabled=True,
            domain=domain,
            role__in=accepted_roles,
        )
        .filter(Q(user=user) | Q(group__user=user))
        .values_list("project_id", flat=True)
        .distinct()
    )


def require_project_role(user, project: Project, domain: str, minimum_role: str) -> None:
    """Raise the shared permission error when a project role is insufficient."""

    if not has_project_role(user, project, domain, minimum_role):
        raise PermissionDenied(
            detail={
                "detail": "You do not have the required project role.",
                "code": "PROJECT_ROLE_REQUIRED",
            }
        )


def accessible_projects(user):
    """Return enabled projects for which the user has any effective domain role."""

    projects = Project.objects.filter(enabled=True)
    if not user or not user.is_authenticated:
        return projects.none()
    if user.is_superuser:
        return projects
    return projects.filter(
        Q(role_assignments__user=user) | Q(role_assignments__group__user=user)
    ).distinct()
