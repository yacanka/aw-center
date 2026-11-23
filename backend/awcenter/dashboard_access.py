"""Enforce the Certification Dashboard scope for restricted Django sessions."""

from django.db.models import Q
from django.db.models.fields.json import KeyTextTransform
from django.http import JsonResponse

from compliance.api import ProjectComplianceMixin
from compliance.dashboard_access import DASHBOARD_DOORS_MODULE_KEY, dashboard_doors_modules, dashboard_projects
from jobs.models import Job
from orgs.models import ProjectRoleAssignment
from users.dashboard_role import is_dashboard_user

from .api_errors import build_error_payload


DASHBOARD_ROUTES = frozenset({
    "api/session/",
    "api/users/password-reset/",
    "api/users/password-reset/confirm/",
    "api/users/invitations/inspect/",
    "api/users/invitations/accept/",
    "api/projects/",
    "api/tools/word/analysis-checks/",
    "api/tools/word/analysis-checks/<uuid:check_id>/",
    "api/tools/word/jobs/analyze/",
    "api/tools/excel/get_excel_columns/",
    "api/tools/excel/jobs/cover-pages/",
    # Both integration actions enforce a Compliance role and project ownership.
    "api/integrations/docproof/search/",
    "api/integrations/doors/module-export-jobs/",
})
DASHBOARD_JOB_DETAIL = "api/jobs/<uuid:job_id>/"
DASHBOARD_JOB_ROUTES = frozenset({
    DASHBOARD_JOB_DETAIL,
    "api/jobs/<uuid:job_id>/cancel/",
    "api/jobs/<uuid:job_id>/download/",
})


class DashboardAccessMiddleware:
    """Allow explicit Certification Dashboard APIs while preserving native CSRF checks."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        route = match.route
        if match.app_name != "admin" and not route.startswith("api/"):
            return None
        if route in DASHBOARD_ROUTES:
            return None
        if (
            route.startswith("api/projects/<slug:project_slug>/compliance-documents/")
            and issubclass(getattr(view_func, "cls", object), ProjectComplianceMixin)
        ):
            return None
        if route == "api/users/preferences/" and request.method in {"GET", "HEAD", "PATCH", "OPTIONS"}:
            return None
        if not is_dashboard_user(request.user):
            return None
        if route in DASHBOARD_JOB_ROUTES:
            if can_access_dashboard_job(
                request.user, view_kwargs["job_id"], include_doors=route == DASHBOARD_JOB_DETAIL,
            ):
                return None
            return JsonResponse(build_error_payload({"detail": "Not found."}, 404), status=404)

        payload = build_error_payload(
            {"detail": "This account can only access Certification Dashboard features."},
            403, code="DASHBOARD_ACCESS_REQUIRED",
        )
        return JsonResponse(payload, status=403)


def can_access_dashboard_job(user, job_id, *, include_doors):
    """Keep shared job controls owner-bound, with live project access for scoped jobs."""

    editable_projects = dashboard_projects(user, ProjectRoleAssignment.Role.EDITOR)
    scope = (
        Q(
            kind__in=("word.analyze", "excel.cover_pages"),
            workflow_run__isnull=True, source_job__isnull=True, jira_issue_draft__isnull=True,
        )
        | Q(kind="compliance.describe_numbering_format", dashboard_project__in=editable_projects.values("slug"))
        | Q(kind="compliance.allocate_cover_page_number", cover_page_number_allocations__project__in=editable_projects)
    )
    if include_doors:
        # DOORS content is available only through project-scoped import views.
        scope |= Q(kind="doors.run_dxl", dashboard_module__in=dashboard_doors_modules(user).values("module_path"))

    return Job.objects.filter(pk=job_id, owner=user).alias(
        dashboard_project=KeyTextTransform("project_slug", "parameters"),
        dashboard_module=KeyTextTransform(DASHBOARD_DOORS_MODULE_KEY, "parameters"),
    ).filter(scope).exists()
