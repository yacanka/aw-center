"""DRF view factory for project compliance-document dashboards."""

from rest_framework.response import Response
from rest_framework.views import APIView

from common.compdoc_dashboard import build_compdoc_dashboard
from common.compdoc_permissions import StrictDjangoModelPermissions


def compdoc_dashboard_view_factory(model, view_permission_classes):
    """Create a project-model-bound, permission-protected dashboard view."""

    class CompDocDashboardView(APIView):
        queryset = model.objects.none()
        permission_classes = [*view_permission_classes, StrictDjangoModelPermissions]

        def get(self, request):
            """Return complete analytics for the bound project model."""

            queryset = model.objects.values("panel", "status_flow")
            return Response(build_compdoc_dashboard(queryset))

    return CompDocDashboardView
