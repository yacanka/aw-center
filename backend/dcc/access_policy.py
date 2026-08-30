"""DCC ownership and project-role authorization policy."""

from django.db.models import Count, F, Q, Subquery
from rest_framework.exceptions import PermissionDenied

from orgs.access_policy import has_role_for_all_projects
from orgs.models import Project, ProjectRoleAssignment

DCC_DOMAIN = ProjectRoleAssignment.Domain.DCC
VIEWER = ProjectRoleAssignment.Role.VIEWER
OPERATOR = ProjectRoleAssignment.Role.OPERATOR
PUBLISHER = ProjectRoleAssignment.Role.PUBLISHER


def is_subject(user, resource):
    """Return whether a user owns or is explicitly assigned to a resource."""

    if user.is_superuser:
        return True
    if resource.owner_id == user.pk:
        return True
    return resource.assigned_users.filter(pk=user.pk).exists()


def resource_projects(resource):
    projects = list(resource.projects.all().order_by("pk"))
    if any(not project.enabled for project in projects):
        return []
    return projects


def has_resource_role(user, resource, minimum_role):
    projects = resource_projects(resource)
    if not projects:
        return False
    if user.is_superuser:
        return True
    return is_subject(user, resource) and has_role_for_all_projects(
        user,
        projects,
        DCC_DOMAIN,
        minimum_role,
    )


def require_resource_role(user, resource, minimum_role):
    if not has_resource_role(user, resource, minimum_role):
        raise PermissionDenied(
            detail={
                "detail": "You do not have the required DCC project role.",
                "code": "DCC_PROJECT_ROLE_REQUIRED",
            }
        )


def require_projects_role(user, projects, minimum_role):
    project_list = list(projects)
    allowed = bool(project_list) and (
        user.is_superuser
        or has_role_for_all_projects(user, project_list, DCC_DOMAIN, minimum_role)
    )
    if not allowed:
        raise PermissionDenied(
            detail={
                "detail": "You do not have the required DCC project role.",
                "code": "DCC_PROJECT_ROLE_REQUIRED",
            }
        )


def project_records_for_user(user):
    """Return subject-bound records readable across every enabled project in SQL."""

    records = DccRecord.objects.prefetch_related("projects", "assigned_users").annotate(
        dcc_project_count=Count("projects", distinct=True),
        dcc_enabled_project_count=Count(
            "projects",
            filter=Q(projects__enabled=True),
            distinct=True,
        ),
    ).filter(
        dcc_project_count__gt=0,
        dcc_project_count=F("dcc_enabled_project_count"),
    )
    if user.is_superuser:
        return records
    allowed_projects = ProjectRoleAssignment.objects.filter(
        Q(user=user) | Q(group__user=user),
        domain=DCC_DOMAIN,
        role__in=ProjectRoleAssignment.VALID_ROLES[DCC_DOMAIN],
        project__enabled=True,
    ).values("project_id")
    return records.filter(Q(owner=user) | Q(assigned_users=user)).annotate(
        dcc_allowed_project_count=Count(
            "projects",
            filter=Q(projects__in=Subquery(allowed_projects)),
            distinct=True,
        )
    ).filter(dcc_project_count=F("dcc_allowed_project_count")).distinct()


def enabled_projects_by_ids(project_ids):
    identifiers = {str(value) for value in project_ids}
    projects = list(Project.objects.filter(pk__in=identifiers, enabled=True).order_by("pk"))
    if not identifiers or {str(project.pk) for project in projects} != identifiers:
        raise PermissionDenied(
            detail={
                "detail": "Select at least one enabled project.",
                "code": "DCC_PROJECT_REQUIRED",
            }
        )
    return projects


from .models import DccRecord  # noqa: E402
