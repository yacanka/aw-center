"""DRF view factory for project compliance-document dashboards."""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from common.compdoc_dashboard import build_compdoc_dashboard
from common.compdoc_permissions import StrictDjangoModelPermissions
from common.compdoc_risk import get_dashboard_value_fields
from common.compdoc_tracking_dashboard import build_tracking_summary
from common.compdoc_lifecycle_models import CompDocReviewTask


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
            payload["operations"] = _operational_summary(model)
            return Response(payload)

    return CompDocDashboardView

def _operational_summary(model):
    today = timezone.localdate()
    documents = model.objects.aggregate(
        unassigned=Count(
            "pk",
            filter=Q(is_archived=False, owner__isnull=True, owner_group__isnull=True),
        ),
        action_overdue=Count(
            "pk", filter=Q(is_archived=False, next_action_due_date__lt=today)
        ),
        action_due_soon=Count(
            "pk",
            filter=Q(
                is_archived=False,
                next_action_due_date__range=(today, today + timedelta(days=7)),
            ),
        ),
        archived=Count("pk", filter=Q(is_archived=True)),
    )
    reviews = CompDocReviewTask.objects.filter(
        project_slug=model._meta.app_label,
        status=CompDocReviewTask.Status.PENDING,
    ).aggregate(
        pending_review=Count("pk", filter=Q(kind=CompDocReviewTask.Kind.REVIEW)),
        pending_approval=Count("pk", filter=Q(kind=CompDocReviewTask.Kind.APPROVAL)),
    )
    return {
        **documents,
        **reviews,
        "filters": {
            "unassigned": {"unassigned": "true"},
            "action_overdue": {"due": "overdue"},
            "action_due_soon": {"due": "soon"},
            "pending_review": {"review": "review"},
            "pending_approval": {"review": "approval"},
            "archived": {"archived": "true"},
        },
    }
