"""Authenticated project catalog joined from business and technical sources."""

from django.utils.cache import patch_cache_control
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orgs.access_policy import accessible_projects, authorized_project_ids, effective_role
from orgs.models import Project, ProjectRoleAssignment
from users.dashboard_role import is_dashboard_user

from .configuration import inspect_project_fields
from .constants import ALLOWED_PROJECT_CAPABILITIES
from .registry import PROJECT_DEFINITIONS, get_project_definitions_by_capability


def _capability_filter(raw_value: str | None) -> str:
    value = (raw_value or "").strip().lower()
    if value and value not in ALLOWED_PROJECT_CAPABILITIES:
        raise ValidationError({"capability": "Use a documented project capability."})
    return value


def serialize_project(project, user, capabilities) -> dict:
    return {
        "slug": project.slug,
        "name": project.name,
        "capabilities": list(capabilities),
        "roles": {
            domain: (
                effective_role(user, project, domain)
                if domain in capabilities
                else None
            )
            for domain in (
                ProjectRoleAssignment.Domain.COMPLIANCE,
                ProjectRoleAssignment.Domain.ORGANIZATION,
                ProjectRoleAssignment.Domain.JIRA,
            )
        },
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def project_catalog(request):
    """Return only enabled, installed and role-accessible projects."""

    capability = _capability_filter(request.query_params.get("capability"))
    dashboard_only = is_dashboard_user(request.user)
    if dashboard_only and capability and capability != ProjectRoleAssignment.Domain.COMPLIANCE:
        return Response([])
    projects = accessible_projects(request.user).filter(
        slug__in=PROJECT_DEFINITIONS
    ).order_by("name", "slug")
    if dashboard_only:
        capability = ProjectRoleAssignment.Domain.COMPLIANCE
        projects = projects.filter(pk__in=authorized_project_ids(
            request.user, capability, ProjectRoleAssignment.Role.VIEWER,
        ))
    payload = []
    for project in projects:
        definition = PROJECT_DEFINITIONS[project.slug]
        if capability and capability not in definition.capabilities:
            continue
        capabilities = (capability,) if dashboard_only else definition.capabilities
        payload.append(serialize_project(project, request.user, capabilities))
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def project_overview(request):
    """Project inventory. Only unrestricted system administrators see private values."""
    if is_dashboard_user(request.user):
        raise PermissionDenied()
    admin = request.user.is_superuser
    projects = Project.objects.all() if admin else accessible_projects(request.user)
    projects = projects.filter(slug__in=PROJECT_DEFINITIONS).order_by("name", "slug")
    items = []
    for project in projects:
        capabilities = PROJECT_DEFINITIONS[project.slug].capabilities
        item = serialize_project(project, request.user, capabilities)
        if admin or any(item["roles"].values()):
            items.append({**item, "enabled": project.enabled})
    fields = {}
    if any("jira" in item["capabilities"] for item in items):
        fields = inspect_project_fields(
            [project.slug for project in get_project_definitions_by_capability("jira")],
            include_values=admin,
        )
    for item in items:
        item["configuration"] = fields.get(item["slug"], {})
    response = Response(items)
    patch_cache_control(response, private=True, no_store=True)
    return response
