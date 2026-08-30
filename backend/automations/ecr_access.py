"""Owner and project-role policy for ECR workflows."""

from django.db.models import Count, F, Q, Subquery
from rest_framework.exceptions import PermissionDenied

from orgs.access_policy import has_role_for_all_projects
from orgs.models import ProjectRoleAssignment

DCC_DOMAIN = ProjectRoleAssignment.Domain.DCC
VIEWER = ProjectRoleAssignment.Role.VIEWER
OPERATOR = ProjectRoleAssignment.Role.OPERATOR
PUBLISHER = ProjectRoleAssignment.Role.PUBLISHER


def has_ecr_role(user, workflow, minimum_role) -> bool:
    """Require ownership plus the DCC role on every enabled project."""

    if not user or not user.is_authenticated:
        return False
    projects = list(workflow.projects.all().order_by("slug"))
    if not projects or any(not project.enabled for project in projects):
        return False
    if user.is_superuser:
        return True
    return workflow.owner_id == user.pk and has_role_for_all_projects(
        user,
        projects,
        DCC_DOMAIN,
        minimum_role,
    )


def require_ecr_role(user, workflow, minimum_role) -> None:
    """Reject an ECR transition without disclosing project internals."""

    if not has_ecr_role(user, workflow, minimum_role):
        raise PermissionDenied(
            detail={
                "detail": "You do not have the required DCC project role.",
                "code": "DCC_PROJECT_ROLE_REQUIRED",
            }
        )


def require_ecr_projects_role(user, projects, minimum_role) -> None:
    """Authorize creation against every selected project."""

    project_list = list(projects)
    allowed = bool(project_list) and (
        user.is_superuser
        or has_role_for_all_projects(
            user,
            project_list,
            DCC_DOMAIN,
            minimum_role,
        )
    )
    if not allowed:
        raise PermissionDenied(
            detail={
                "detail": "You do not have the required DCC project role.",
                "code": "DCC_PROJECT_ROLE_REQUIRED",
            }
        )


def readable_ecr_workflows(user, queryset):
    """Return owned workflows whose every project remains readable in SQL."""

    owned = queryset.filter(owner=user)
    if user.is_superuser:
        return owned
    allowed_projects = ProjectRoleAssignment.objects.filter(
        Q(user=user) | Q(group__user=user),
        domain=DCC_DOMAIN,
        role__in=ProjectRoleAssignment.VALID_ROLES[DCC_DOMAIN],
        project__enabled=True,
    ).values("project_id")
    return (
        owned.annotate(
            ecr_project_count=Count("projects", distinct=True),
            ecr_allowed_project_count=Count(
                "projects",
                filter=Q(projects__in=Subquery(allowed_projects)),
                distinct=True,
            ),
        )
        .filter(
            ecr_project_count__gt=0,
            ecr_project_count=F("ecr_allowed_project_count"),
        )
    )
