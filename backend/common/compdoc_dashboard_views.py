"""DRF view factory for project compliance-document dashboards."""

from rest_framework.response import Response
from rest_framework.views import APIView

from common.compdoc_dashboard import build_compdoc_dashboard
from common.compdoc_permissions import StrictDjangoModelPermissions
from common.compdoc_risk import get_dashboard_value_fields
from common.compdoc_tracking_dashboard import build_tracking_summary
from common.compdoc_operations_summary import build_operational_summary


def compdoc_dashboard_view_factory(model, view_permission_classes):
    """Create a project-model-bound, permission-protected dashboard view."""

    class CompDocDashboardView(APIView):
        queryset = model.objects.none()
        permission_classes = [*view_permission_classes, StrictDjangoModelPermissions]

        def get(self, request):
            """Return complete analytics for the bound project model."""

            queryset = model.objects.filter(is_archived=False).values(
                *get_dashboard_value_fields(model)
            )
            panel_model = model._meta.apps.get_model(model._meta.app_label, "Panel")
            valid_panel_pairs = set(panel_model.objects.values_list("name", "ata"))
            payload = build_compdoc_dashboard(
                queryset, valid_panel_pairs=valid_panel_pairs
            )
            payload["tracking"] = build_tracking_summary(model)
            payload["operations"] = build_operational_summary(model)
            return Response(payload)

    return CompDocDashboardView
