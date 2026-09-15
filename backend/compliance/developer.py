"""Explicit, development-only reset of compliance and organization test data."""

import logging

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from jobs.models import Job, JobStatus
from orgs.models import Panel, Person, Project, ProjectRoleAssignment, ResponsibleAssignment

from .models import (
    ComplianceDocument, CoverPage, CoverPageNumberAllocation, DocumentPurgeAudit,
    DoorsImportMapping, ImportAudit, NotificationLog, NotificationPolicy, ReviewTask,
    TrackingProfile, WorkflowEvent,
)

logger = logging.getLogger(__name__)
RESET_PHRASE = "RESET COMPLIANCE AND ORGANIZATION"
TOKEN_SALT = "compliance.developer-reset"


def _reset_querysets():
    """Keep the deletion order explicit; preserve project catalog, users and DCC roles."""
    return {
        "number_allocations": CoverPageNumberAllocation.objects.all(),
        "notification_logs": NotificationLog.objects.all(),
        "tracking_profiles": TrackingProfile.objects.all(),
        "reviews": ReviewTask.objects.all(),
        "workflow_events": WorkflowEvent.objects.all(),
        "documents": ComplianceDocument.objects.all(),
        "cover_pages": CoverPage.objects.all(),
        "document_history": ComplianceDocument.history.all(),
        "cover_page_history": CoverPage.history.all(),
        "import_audits": ImportAudit.objects.all(),
        "purge_audits": DocumentPurgeAudit.objects.all(),
        "doors_import_mappings": DoorsImportMapping.objects.all(),
        "notification_policies": NotificationPolicy.objects.all(),
        "responsible_assignments": ResponsibleAssignment.objects.all(),
        "panels": Panel.objects.all(),
        "people": Person.objects.all(),
        "project_roles": ProjectRoleAssignment.objects.filter(
            domain__in=[ProjectRoleAssignment.Domain.COMPLIANCE, ProjectRoleAssignment.Domain.ORGANIZATION]
        ),
    }


def _counts():
    return {name: queryset.count() for name, queryset in _reset_querysets().items()}


class DevelopmentSuperuser(BasePermission):
    def has_permission(self, request, view):
        if not settings.DEBUG or settings.AWCENTER_DEPLOYMENT_MODE != "development":
            raise NotFound()
        if not request.user.is_superuser:
            raise PermissionDenied("Only a superuser can reset test data.")
        return True


class DeveloperResetView(APIView):
    """Preview all-project deletion and require a short-lived, user-bound confirmation."""

    permission_classes = [IsAuthenticated, DevelopmentSuperuser]

    def get(self, request):
        counts = _counts()
        return Response({
            "counts": counts,
            "confirmation_phrase": RESET_PHRASE,
            "confirmation_token": signing.dumps(
                {"user": request.user.pk, "counts": counts}, salt=TOKEN_SALT,
            ),
        })

    def post(self, request):
        if request.data.get("confirmation_phrase") != RESET_PHRASE:
            raise ValidationError({"detail": "Enter the exact reset confirmation phrase."})
        try:
            preview = signing.loads(
                request.data.get("confirmation_token", ""), salt=TOKEN_SALT, max_age=300,
            )
        except (signing.BadSignature, TypeError, ValueError):
            raise ValidationError({"detail": "Reset preview expired or is invalid. Reload the preview."})
        if preview.get("user") != request.user.pk:
            raise PermissionDenied("Reset preview belongs to another user.")
        try:
            with transaction.atomic():
                list(Project.objects.select_for_update().values_list("pk", flat=True))
                self._require_idle_workers()
                counts = _counts()
                if counts != preview.get("counts"):
                    raise ValidationError({"detail": "Data counts changed. Reload the reset preview."})
                for queryset in _reset_querysets().values():
                    queryset.delete()
        except ProtectedError:
            raise ValidationError({"detail": "Other records reference this data. No data was reset."})
        logger.warning("Developer compliance/organization reset completed: counts=%s", counts)
        return Response({"detail": "Compliance documents and organization test data were reset.", "counts": counts})

    @staticmethod
    def _require_idle_workers():
        # A pending allocation may still carry an upstream number reservation even
        # after its job has stopped. Require reconciliation before losing that state.
        active_jobs = Job.objects.exclude(status__in=[
            JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED,
        ]).exists()
        pending_allocations = CoverPageNumberAllocation.objects.exclude(
            status=CoverPageNumberAllocation.Status.COMPLETED,
        ).exists()
        if active_jobs or pending_allocations:
            raise ValidationError({"detail": "Finish or cancel active jobs and reconcile pending number allocations before resetting."})
