"""Project authorization for integrations reachable from Certification Dashboard."""

from django.db.models import Q

from orgs.access_policy import authorized_project_ids
from orgs.models import Project, ProjectRoleAssignment
from projects.registry import get_project_definitions_by_capability

from .models import ComplianceDocument, DoorsImportMapping


DASHBOARD_DOORS_MODULE_KEY = "dashboard_doors_module"


def dashboard_projects(user, minimum_role):
    """Scope integration access to enabled projects supporting Compliance Documents."""

    compliance = ProjectRoleAssignment.Domain.COMPLIANCE
    return Project.objects.filter(
        slug__in=[definition.slug for definition in get_project_definitions_by_capability(compliance)],
        pk__in=authorized_project_ids(user, compliance, minimum_role),
    )


def dashboard_doors_modules(user):
    """Only previously mapped project modules may use the shared DOORS worker."""

    return DoorsImportMapping.objects.filter(
        project__in=dashboard_projects(user, ProjectRoleAssignment.Role.EDITOR),
    )


def dashboard_can_search_document(user, raw_number, document_number):
    """Match the DocProof identifier or its original register value in a readable project."""

    if not document_number or len(document_number) > 64:
        return False
    return ComplianceDocument.objects.filter(
        project__in=dashboard_projects(user, ProjectRoleAssignment.Role.VIEWER),
    ).filter(
        Q(number__iexact=raw_number) | Q(number__iexact=document_number)
        | Q(number__istartswith=f"{document_number}/")
    ).exists()
