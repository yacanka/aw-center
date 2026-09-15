"""Explicit, development-only reset of compliance and organization test data."""

import logging
import uuid

from django.conf import settings
from django.core import signing
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from jobs.models import Job, JobStatus
from jobs.services import request_cancellation
from jobs.worker import recover_expired_job
from orgs.models import Panel, Person, Project, ProjectRoleAssignment, ResponsibleAssignment

from .models import (
    ComplianceDocument, CoverPage, CoverPageNumberAllocation, DocumentPurgeAudit,
    DoorsImportMapping, ImportAudit, NotificationLog, NotificationPolicy, ReviewTask,
    TrackingProfile, WorkflowEvent,
)
from .reset_guard import lock_reset_state

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


# Only this executor writes reset-owned database records. Other tools generate
# artifacts or update independent external systems and must not block this reset.
RESET_JOB_KIND = "compliance.allocate_cover_page_number"
ACTIVE_STATUSES = [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED,
                   JobStatus.AWAITING_CONFIRMATION]


def _related_jobs():
    return Job.objects.filter(
        Q(kind=RESET_JOB_KIND) | Q(cover_page_number_allocations__isnull=False)
    ).distinct()


def _safe_unstarted_allocations():
    # No lease has ever been claimed, no retry/resume took place, and no remote
    # evidence exists. Cancelling these intents cannot abandon a reservation.
    return CoverPageNumberAllocation.objects.filter(
        status=CoverPageNumberAllocation.Status.REQUESTED,
        version=1,
        remote_id__isnull=True,
        remote_number="",
        remote_status="",
        remote_request_id="",
        current_job__status=JobStatus.CANCELLED,
        current_job__started_at__isnull=True,
        current_job__attempt=1,
    )


def _blockers():
    jobs = _related_jobs().filter(status__in=ACTIVE_STATUSES)
    allocations = CoverPageNumberAllocation.objects.exclude(
        status=CoverPageNumberAllocation.Status.COMPLETED,
    ).exclude(pk__in=_safe_unstarted_allocations().values("pk"))
    # Old uncertain attempts remain in Job history after a successful resume.
    # Only an allocation's current unresolved job belongs to this reset's blockers.
    uncertain = _related_jobs().filter(
        status=JobStatus.RECONCILIATION_REQUIRED, cover_page_number_allocations__isnull=False,
    ).exclude(
        cover_page_number_allocations__status=CoverPageNumberAllocation.Status.COMPLETED,
    )
    notifications = NotificationLog.objects.filter(status=NotificationLog.Status.CLAIMED)
    # Return bounded, content-free diagnostics. Total counts always determine readiness.
    return {
        "jobs": list(jobs.values("id", "kind", "status")[:100]),
        "job_count": jobs.count(),
        "uncertain_jobs": list(uncertain.values("id", "kind", "status")[:100]),
        "uncertain_job_count": uncertain.count(),
        "allocations": list(allocations.values("id", "project__slug", "status", "current_job_id")[:100]),
        "allocation_count": allocations.count(),
        "notification_count": notifications.count(),
    }


def _is_blocked(blockers):
    return any(blockers[key] for key in (
        "job_count", "uncertain_job_count", "allocation_count", "notification_count",
    ))


def _preview(user, state):
    counts = _counts()
    blockers = _blockers()
    return {
        "counts": counts,
        "prepared": state.active,
        "ready": state.active and not _is_blocked(blockers),
        "blockers": blockers,
        "confirmation_phrase": RESET_PHRASE,
        "confirmation_token": signing.dumps(
            {"user": user.pk, "counts": counts, "generation": str(state.generation)},
            salt=TOKEN_SALT,
        ),
    }


class DeveloperResetView(APIView):
    """Prepare/cancel/release separately from the explicit, atomic deletion."""

    permission_classes = [IsAuthenticated, DevelopmentSuperuser]

    def get(self, request):
        with lock_reset_state() as state:
            return Response(_preview(request.user, state))

    def post(self, request):
        action = request.data.get("action", "reset")
        if action not in {"prepare", "release", "reset"}:
            raise ValidationError({"detail": "Unknown reset action."})
        if action == "reset" and request.data.get("confirmation_phrase") != RESET_PHRASE:
            raise ValidationError({"detail": "Enter the exact reset confirmation phrase."})
        preview = self._read_token(request)
        try:
            with lock_reset_state() as state:
                if preview.get("generation") != str(state.generation):
                    raise ValidationError({"detail": "Reset preparation changed. Reload the preview."})
                if action == "prepare":
                    self._prepare(state)
                    return Response(_preview(request.user, state))
                if action == "release":
                    self._release(state)
                    return Response(_preview(request.user, state))
                counts = self._reset(state, preview)
        except ProtectedError:
            raise ValidationError({"detail": "Other records reference this data. No data was reset."})
        logger.warning("Developer compliance/organization reset completed: counts=%s", counts)
        return Response({"detail": "Compliance documents and organization test data were reset.", "counts": counts})

    @staticmethod
    def _read_token(request):
        try:
            preview = signing.loads(
                request.data.get("confirmation_token", ""), salt=TOKEN_SALT, max_age=300,
            )
        except (signing.BadSignature, TypeError, ValueError):
            raise ValidationError({"detail": "Reset preview expired or is invalid. Reload the preview."})
        if preview.get("user") != request.user.pk:
            raise PermissionDenied("Reset preview belongs to another user.")
        return preview

    @staticmethod
    def _prepare(state):
        if not state.active:
            state.active = True
            state.generation = uuid.uuid4()
            state.save()
        # Cancel before recovery so an abandoned lease cannot requeue new work.
        for job in _related_jobs().filter(status__in=ACTIVE_STATUSES):
            if job.status == JobStatus.AWAITING_CONFIRMATION:
                continue
            request_cancellation(job)
            recover_expired_job(job.pk)

    @staticmethod
    def _release(state):
        state.active = False
        state.generation = uuid.uuid4()
        state.save()

    def _reset(self, state, preview):
        if not state.active:
            raise ValidationError({"detail": "Prepare the reset before deleting test data."})
        list(Project.objects.select_for_update().values_list("pk", flat=True))
        if _is_blocked(_blockers()):
            raise ValidationError({"detail": "Reset is blocked. Refresh the preview to inspect jobs, allocations and notifications."})
        counts = _counts()
        if counts != preview.get("counts"):
            raise ValidationError({"detail": "Data counts changed. Reload the reset preview."})
        for queryset in _reset_querysets().values():
            queryset.delete()
        self._release(state)
        return counts
