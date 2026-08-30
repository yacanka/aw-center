"""Project-scoped HTTP API for canonical compliance documents."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from requests.exceptions import RequestException

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.file_security import OOXML_WORKBOOK_POLICY, validate_request_upload
from awcenter.api_errors import error_response
from awcenter.pagination import StandardResultsSetPagination
from awcenter.spreadsheet_security import spreadsheet_safe_rows
from jobs.models import Job, JobStatus
from orgs.access_policy import has_project_role, require_project_role
from orgs.models import Project, ProjectRoleAssignment
from projects.registry import PROJECT_DEFINITIONS

from .compdoc_workflow import WORKFLOW_STATUSES
from .doors_imports import (
    create_doors_confirmation,
    default_mapping,
    execute_doors_plan,
    load_doors_source,
    prepare_doors_plan,
    validate_mapping,
    verify_doors_confirmation,
)
from .imports import (
    IMPORT_FIELDS,
    create_confirmation,
    execute_plan,
    prepare_plan,
    verify_confirmation,
)
from .models import (
    ComplianceDocument,
    ImportAudit,
    NotificationPolicy,
    ReviewTask,
    TrackingProfile,
    WorkflowEvent,
)
from .serializers import (
    ComplianceDocumentSerializer,
    ImportAuditSerializer,
    ReviewTaskSerializer,
    TrackingProfileSerializer,
    WorkflowEventSerializer,
)
from .services import (
    VersionConflict,
    decide_review,
    request_review,
    refresh_docproof_tracking,
    set_archive_state,
    transition_document,
    update_document,
    update_tracking_profile,
    update_work,
)


TEXT_FILTER_FIELDS = frozenset(
    {
        "name",
        "cover_page_no",
        "cover_page_issue",
        "tech_doc_no",
        "tech_doc_issue",
        "delivered_tech_doc_issue",
        "tech_doc_no_2",
        "tech_doc_issue_2",
        "delivered_tech_doc_issue_2",
        "responsible",
        "moc",
        "mom_no",
        "path",
    }
)
SELECT_FILTER_FIELDS = frozenset({"panel", "status", "cat"})
DATE_FILTER_FIELDS = frozenset(
    {"ubm_target_date", "ubm_delivery_date", "next_action_due_date", "created_at", "updated_at"}
)
FILTER_FIELD_LOOKUPS = {
    "cover_page_no": "cover_page__number",
    "cover_page_issue": "cover_page__issue",
}
ORDERING_FIELDS = {
    **{field: FILTER_FIELD_LOOKUPS.get(field, field) for field in TEXT_FILTER_FIELDS},
    **{field: field for field in SELECT_FILTER_FIELDS | DATE_FILTER_FIELDS},
    "ata": "panel__ata",
    "is_archived": "is_archived",
}
DATE_FILTER_SUFFIXES = {"": "", "__not": "", "__gt": "__gt", "__gte": "__gte", "__lt": "__lt", "__lte": "__lte"}


class ProjectComplianceMixin:
    permission_classes = [IsAuthenticated]
    minimum_role = ProjectRoleAssignment.Role.VIEWER
    project = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.project = get_object_or_404(
            Project,
            slug=kwargs["project_slug"],
            enabled=True,
        )
        definition = PROJECT_DEFINITIONS.get(self.project.slug)
        if definition is None or "compliance" not in definition.capabilities:
            raise Http404
        require_project_role(
            request.user,
            self.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            self.minimum_role,
        )

    def serializer_context(self):
        return {"request": self.request, "project": self.project}

    def document(self, document_id, *, include_archived=True):
        queryset = ComplianceDocument.objects.filter(project=self.project)
        if not include_archived:
            queryset = queryset.filter(is_archived=False)
        return get_object_or_404(
            queryset.select_related("project", "panel", "cover_page", "owner", "owner_group"),
            pk=document_id,
        )


class DocumentCollectionView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug):
        queryset = ComplianceDocument.objects.filter(project=self.project).select_related(
            "project", "panel", "cover_page", "owner", "owner_group"
        )
        archived = request.query_params.get("archived")
        if archived == "true":
            queryset = queryset.filter(is_archived=True)
        elif archived != "all":
            queryset = queryset.filter(is_archived=False)
        search = request.query_params.get("search", "").strip()[:200]
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(cover_page__number__icontains=search)
                | Q(tech_doc_no__icontains=search)
                | Q(tech_doc_no_2__icontains=search)
            )
        queryset = _apply_document_filters(queryset, request.query_params)
        queryset = _apply_document_ordering(queryset, request.query_params.get("ordering"))
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = ComplianceDocumentSerializer(
            page,
            many=True,
            context=self.serializer_context(),
        )
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, project_slug):
        require_project_role(
            request.user,
            self.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.EDITOR,
        )
        serializer = ComplianceDocumentSerializer(
            data=request.data,
            context=self.serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DocumentDetailView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug, document_id):
        return Response(
            ComplianceDocumentSerializer(
                self.document(document_id),
                context=self.serializer_context(),
            ).data
        )

    def put(self, request, project_slug, document_id):
        return self._update(request, document_id, partial=False)

    def patch(self, request, project_slug, document_id):
        return self._update(request, document_id, partial=True)

    def _update(self, request, document_id, partial):
        require_project_role(
            request.user,
            self.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.EDITOR,
        )
        expected_version = _expected_version(request.data)
        instance = self.document(document_id, include_archived=False)
        serializer = ComplianceDocumentSerializer(
            instance,
            data=request.data,
            partial=partial,
            context=self.serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        updated = update_document(
            project=self.project,
            document_id=document_id,
            expected_version=expected_version,
            serializer=serializer,
            user=request.user,
        )
        return Response(
            ComplianceDocumentSerializer(updated, context=self.serializer_context()).data
        )


class DocumentHistoryView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug, document_id):
        document = self.document(document_id)
        queryset = document.history.select_related("history_user").order_by(
            "-history_date",
            "-history_id",
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request)
        results = [
            {
                "history_id": row.history_id,
                "version": row.version,
                "history_date": row.history_date,
                "history_type": row.get_history_type_display(),
                "history_user": str(row.history_user or ""),
                "history_change_reason": row.history_change_reason or "",
            }
            for row in page
        ]
        return paginator.get_paginated_response(results)


class DocumentFieldsView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug):
        excluded = {"project", "history", "version"}
        fields = [
            {
                "key": field.name,
                "label": str(field.verbose_name).replace("_", " ").title(),
                "required": not field.blank and not field.null,
                "read_only": not field.editable,
                **_field_capabilities(field.name),
            }
            for field in ComplianceDocument._meta.fields
            if field.name not in excluded
        ]
        return Response(
            {"schema_version": 3, "project": self.project.slug, "fields": fields}
        )


class DashboardView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug):
        active = ComplianceDocument.objects.filter(project=self.project, is_archived=False)
        status_counts = {
            row["status"]: row["count"]
            for row in active.values("status").annotate(count=Count("id"))
        }
        today = timezone.localdate()
        return Response(
            {
                "project": self.project.slug,
                "total": active.count(),
                "archived": ComplianceDocument.objects.filter(
                    project=self.project,
                    is_archived=True,
                ).count(),
                "overdue": active.filter(next_action_due_date__lt=today).count(),
                "status_counts": status_counts,
            }
        )


class TransitionInputSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=sorted(WORKFLOW_STATUSES))
    effective_date = serializers.DateField()
    next_action_due_date = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)


class TransitionView(ProjectComplianceMixin, APIView):
    minimum_role = ProjectRoleAssignment.Role.EDITOR

    def post(self, request, project_slug, document_id):
        serializer = TransitionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        document, event = transition_document(
            project=self.project,
            document_id=document_id,
            expected_version=values["version"],
            new_status=values["status"],
            effective_date=values["effective_date"],
            next_action_due_date=values.get("next_action_due_date"),
            reason=values["reason"],
            user=request.user,
        )
        return Response(
            {"document_id": document.pk, "version": document.version, "event_id": event.pk}
        )


class WorkInputSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    owner = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True),
        allow_null=True,
        required=False,
    )
    owner_group = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(), allow_null=True, required=False
    )
    next_action_due_date = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)


class WorkView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug, document_id):
        document = self.document(document_id)
        return Response(_work_payload(document))

    def put(self, request, project_slug, document_id):
        require_project_role(
            request.user,
            self.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.EDITOR,
        )
        serializer = WorkInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        for subject in (values.get("owner"),):
            if subject and not has_project_role(
                subject,
                self.project,
                ProjectRoleAssignment.Domain.COMPLIANCE,
                ProjectRoleAssignment.Role.VIEWER,
            ):
                raise serializers.ValidationError({"owner": "Owner cannot view this project."})
        updated = update_work(
            project=self.project,
            document_id=document_id,
            expected_version=values.pop("version"),
            values={
                key: values[key]
                for key in ("owner", "owner_group", "next_action_due_date")
                if key in values
            },
            reason=values.pop("reason"),
            user=request.user,
        )
        return Response(_work_payload(updated))


class ArchiveInputSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)


class ArchiveView(ProjectComplianceMixin, APIView):
    minimum_role = ProjectRoleAssignment.Role.MANAGER
    archived = True

    def post(self, request, project_slug, document_id):
        serializer = ArchiveInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        document = set_archive_state(
            project=self.project,
            document_id=document_id,
            expected_version=values["version"],
            archived=self.archived,
            reason=values["reason"],
            user=request.user,
        )
        return Response(
            {"id": document.pk, "is_archived": document.is_archived, "version": document.version}
        )


class RestoreView(ArchiveView):
    archived = False


class ActivityView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug, document_id):
        document = self.document(document_id)
        events = WorkflowEventSerializer(document.workflow_events.all()[:100], many=True).data
        reviews = ReviewTaskSerializer(document.review_tasks.all()[:100], many=True).data
        items = sorted(
            [
                {"type": "workflow", "at": item["created_at"], "data": item}
                for item in events
            ]
            + [
                {"type": "review", "at": item["created_at"], "data": item}
                for item in reviews
            ],
            key=lambda item: item["at"],
            reverse=True,
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(items, request)
        return paginator.get_paginated_response(page)


class ReviewRequestInputSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=ReviewTask.Kind.choices)
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True)
    )
    due_date = serializers.DateField(required=False, allow_null=True)
    request_note = serializers.CharField(min_length=3, max_length=500)


class ReviewCollectionView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug, document_id):
        document = self.document(document_id)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(
            document.review_tasks.select_related("document", "document__project"),
            request,
        )
        return paginator.get_paginated_response(
            ReviewTaskSerializer(
                page,
                many=True,
                context=self.serializer_context(),
            ).data
        )

    def post(self, request, project_slug, document_id):
        require_project_role(
            request.user,
            self.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.EDITOR,
        )
        serializer = ReviewRequestInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        task = request_review(
            project=self.project,
            document_id=document_id,
            expected_version=values["version"],
            kind=values["kind"],
            assignee=values["assignee"],
            due_date=values.get("due_date"),
            request_note=values["request_note"],
            user=request.user,
        )
        return Response(
            ReviewTaskSerializer(task, context=self.serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class ReviewDecisionInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(
            ReviewTask.Status.APPROVED,
            ReviewTask.Status.CHANGES_REQUESTED,
            ReviewTask.Status.CANCELLED,
        )
    )
    decision_note = serializers.CharField(min_length=3, max_length=500)


class ReviewDecisionView(ProjectComplianceMixin, APIView):
    minimum_role = ProjectRoleAssignment.Role.VIEWER

    def post(self, request, project_slug, document_id, review_id):
        serializer = ReviewDecisionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = decide_review(
            project=self.project,
            document_id=document_id,
            review_id=review_id,
            decision=serializer.validated_data["status"],
            note=serializer.validated_data["decision_note"],
            user=request.user,
        )
        return Response(ReviewTaskSerializer(task, context=self.serializer_context()).data)


class TrackingView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug, document_id):
        document = self.document(document_id)
        profile = TrackingProfile.objects.filter(document=document).first()
        if profile is None:
            return Response(_empty_tracking_payload())
        return Response(TrackingProfileSerializer(profile).data)


class DocProofRefreshInputSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=0)


class DocProofRefreshView(ProjectComplianceMixin, APIView):
    minimum_role = ProjectRoleAssignment.Role.EDITOR

    def post(self, request, project_slug, document_id):
        serializer = DocProofRefreshInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = refresh_docproof_tracking(
                project=self.project,
                document_id=document_id,
                expected_version=serializer.validated_data["version"],
                user=request.user,
            )
        except RequestException:
            return error_response(
                "DocProof could not be reached.",
                code="DOCPROOF_UNAVAILABLE",
                response_status=503,
            )
        return Response(TrackingProfileSerializer(profile).data)

    def put(self, request, project_slug, document_id):
        require_project_role(
            request.user,
            self.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.EDITOR,
        )
        profile = update_tracking_profile(
            project=self.project,
            document_id=document_id,
            expected_version=_expected_version(request.data, minimum=0),
            payload=request.data,
            user=request.user,
        )
        return Response(TrackingProfileSerializer(profile).data)


class NotificationPolicyInputSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=0)
    event_rules = serializers.DictField()
    change_note = serializers.CharField(min_length=3, max_length=255)

    def validate_event_rules(self, value):
        from .notifications import SUPPORTED_EVENTS

        unknown = set(value) - SUPPORTED_EVENTS
        if unknown:
            raise serializers.ValidationError("Rules contain unsupported events.")
        normalized = {}
        for event_type, rule in value.items():
            if not isinstance(rule, dict) or set(rule) - {"enabled"}:
                raise serializers.ValidationError(
                    "Each event rule may contain only an enabled boolean."
                )
            enabled = rule.get("enabled", True)
            if not isinstance(enabled, bool):
                raise serializers.ValidationError("Event enabled values must be booleans.")
            normalized[event_type] = {"enabled": enabled}
        return normalized


class NotificationPolicyView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug):
        policy = NotificationPolicy.objects.filter(
            project=self.project,
            is_active=True,
        ).first()
        return Response(
            _notification_policy_payload(
                policy,
                can_manage=has_project_role(
                    request.user,
                    self.project,
                    ProjectRoleAssignment.Domain.COMPLIANCE,
                    ProjectRoleAssignment.Role.MANAGER,
                ),
            )
        )

    def put(self, request, project_slug):
        require_project_role(
            request.user,
            self.project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.MANAGER,
        )
        serializer = NotificationPolicyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            locked_project = get_object_or_404(
                Project.objects.select_for_update(),
                pk=self.project.pk,
                enabled=True,
            )
            policies = NotificationPolicy.objects.filter(project=locked_project)
            active_policy = policies.filter(is_active=True).first()
            current_version = active_policy.version if active_policy else 0
            if serializer.validated_data["version"] != current_version:
                raise VersionConflict("Notification policy changed after you opened it.")
            next_version = (policies.aggregate(value=Max("version"))["value"] or 0) + 1
            policies.filter(is_active=True).update(is_active=False)
            policy = NotificationPolicy.objects.create(
                project=locked_project,
                version=next_version,
                event_rules=serializer.validated_data["event_rules"],
                change_note=serializer.validated_data["change_note"],
                updated_by=request.user,
                updated_by_username=request.user.get_username(),
            )
        return Response(_notification_policy_payload(policy, can_manage=True))


class ImportPreviewView(ProjectComplianceMixin, APIView):
    minimum_role = ProjectRoleAssignment.Role.EDITOR

    def post(self, request, project_slug):
        uploaded_file = validate_request_upload(request, "file", OOXML_WORKBOOK_POLICY)
        plan = prepare_plan(uploaded_file, self.project, request)
        if plan.mapping["missing_columns"]:
            raise serializers.ValidationError(
                {"columns": plan.mapping["missing_columns"]}
            )
        return Response(
            {
                **plan.mapping,
                **plan.counts,
                "invalid_documents": list(plan.errors),
                "confirmation_token": create_confirmation(
                    uploaded_file,
                    request.user,
                    self.project,
                    plan,
                ),
                "database_state_protected": True,
            }
        )


class ImportConfirmView(ProjectComplianceMixin, APIView):
    minimum_role = ProjectRoleAssignment.Role.EDITOR

    def post(self, request, project_slug):
        uploaded_file = validate_request_upload(request, "file", OOXML_WORKBOOK_POLICY)
        fingerprint = verify_confirmation(
            request.data.get("confirmation_token"),
            uploaded_file,
            request.user,
            self.project,
        )
        audit, plan = execute_plan(uploaded_file, self.project, request, fingerprint)
        return Response(
            {
                "detail": "Import completed.",
                "code": "COMPLIANCE_IMPORT_COMPLETED",
                "audit_id": audit.pk,
                "status": audit.status,
                **plan.counts,
                "invalid_documents": list(plan.errors),
            },
            status=status.HTTP_201_CREATED,
        )


class DoorsImportInputSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    mapping = serializers.DictField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
    )
    confirmation_token = serializers.CharField(required=False, allow_blank=True)


class DoorsImportSourceView(ProjectComplianceMixin, APIView):
    minimum_role = ProjectRoleAssignment.Role.EDITOR

    def get(self, request, project_slug, job_id):
        job = _doors_import_job(request, job_id)
        source = load_doors_source(job)
        mapping = default_mapping(self.project, source)
        return Response(
            {
                "job_id": job.pk,
                "module_path": source["module_path"],
                "row_count": len(source["rows"]),
                "columns": source["columns"],
                "default_mapping": mapping,
                "target_fields": [
                    {
                        "key": field,
                        "label": field.replace("_", " ").title(),
                        "required": field in {"name", "cover_page_no"},
                    }
                    for field in sorted(IMPORT_FIELDS)
                ],
            }
        )


class DoorsImportPreviewView(ProjectComplianceMixin, APIView):
    minimum_role = ProjectRoleAssignment.Role.EDITOR

    def post(self, request, project_slug):
        serializer = DoorsImportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        job = _doors_import_job(request, values["job_id"])
        source = load_doors_source(job)
        mapping = validate_mapping(values["mapping"], source["columns"])
        plan = prepare_doors_plan(job, self.project, request, mapping)
        return Response(
            {
                **plan.mapping,
                **plan.counts,
                "job_id": job.pk,
                "module_path": source["module_path"],
                "invalid_documents": list(plan.errors),
                "confirmation_token": create_doors_confirmation(
                    job,
                    mapping,
                    request.user,
                    self.project,
                    plan,
                ),
                "database_state_protected": True,
            }
        )


class DoorsImportConfirmView(ProjectComplianceMixin, APIView):
    minimum_role = ProjectRoleAssignment.Role.EDITOR

    def post(self, request, project_slug):
        serializer = DoorsImportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        job = _doors_import_job(request, values["job_id"])
        source = load_doors_source(job)
        mapping = validate_mapping(values["mapping"], source["columns"])
        fingerprint = verify_doors_confirmation(
            values.get("confirmation_token"),
            job,
            mapping,
            request.user,
            self.project,
        )
        audit, plan = execute_doors_plan(
            job,
            mapping,
            self.project,
            request,
            fingerprint,
        )
        return Response(
            {
                "detail": "DOORS import completed.",
                "code": "COMPLIANCE_DOORS_IMPORT_COMPLETED",
                "audit_id": audit.pk,
                "status": audit.status,
                **plan.counts,
                "invalid_documents": list(plan.errors),
            },
            status=status.HTTP_201_CREATED,
        )


class ImportAuditCollectionView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug):
        queryset = ImportAudit.objects.filter(project=self.project).select_related(
            "imported_by"
        )
        search = request.query_params.get("search", "").strip()[:200]
        if search:
            queryset = queryset.filter(
                Q(source_filename__icontains=search)
                | Q(imported_by__username__icontains=search)
            )
        audit_status = request.query_params.get("status", "").strip()
        if audit_status:
            allowed_statuses = {choice for choice, _label in ImportAudit.Status.choices}
            if audit_status not in allowed_statuses:
                raise serializers.ValidationError(
                    {"status": "Select a supported import-audit status."}
                )
            queryset = queryset.filter(status=audit_status)
        queryset = queryset.order_by("-started_at")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(ImportAuditSerializer(page, many=True).data)


class ImportAuditDetailView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug, audit_id):
        audit = get_object_or_404(ImportAudit, project=self.project, pk=audit_id)
        return Response(ImportAuditSerializer(audit).data)


class ExportView(ProjectComplianceMixin, APIView):
    def get(self, request, project_slug):
        import pandas as pd

        queryset = ComplianceDocument.objects.filter(
            project=self.project,
            is_archived=False,
        )
        export_limit = max(1, int(settings.AWCENTER_MAX_COMPDOC_EXPORT_ROWS))
        if queryset.order_by().values("pk")[: export_limit + 1].count() > export_limit:
            return error_response(
                "The compliance-document export exceeds the configured row limit.",
                "COMPDOC_EXPORT_ROW_LIMIT",
                response_status=413,
            )
        latest_effective_date = WorkflowEvent.objects.filter(
            document_id=OuterRef("pk"),
        ).order_by("-sequence").values("effective_date")[:1]
        documents = queryset.select_related("panel", "cover_page").annotate(
            current_effective_date=Subquery(latest_effective_date)
        )
        rows = spreadsheet_safe_rows([_export_document_row(document) for document in documents])
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{self.project.slug}-compliance-documents.xlsx"'
        )
        with pd.ExcelWriter(response, engine="openpyxl") as writer:
            pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Compliance Documents")
        return response


def _export_document_row(document):
    return {
        "id": str(document.pk),
        "name": document.name,
        "panel": document.panel.ata if document.panel else "",
        "signature_panel": "; ".join(document.signature_panel or ()),
        "cover_page_no": document.cover_page.number,
        "cover_page_issue": document.cover_page.issue,
        "tech_doc_no": document.tech_doc_no,
        "tech_doc_issue": document.tech_doc_issue,
        "delivered_tech_doc_issue": document.delivered_tech_doc_issue,
        "tech_doc_no_2": document.tech_doc_no_2,
        "tech_doc_issue_2": document.tech_doc_issue_2,
        "delivered_tech_doc_issue_2": document.delivered_tech_doc_issue_2,
        "responsible": document.responsible,
        "cat": document.cat,
        "moc": document.moc,
        "mom_no": document.mom_no,
        "requirements": "; ".join(document.requirements or ()),
        "status": document.status,
        "effective_date": document.current_effective_date,
        "path": document.path,
        "notes": document.notes,
    }


def _expected_version(payload, *, minimum=1):
    try:
        value = int(payload.get("version"))
    except (TypeError, ValueError) as error:
        raise serializers.ValidationError(
            {"version": f"A current version of at least {minimum} is required."}
        ) from error
    if value < minimum:
        raise serializers.ValidationError(
            {"version": f"A current version of at least {minimum} is required."}
        )
    return value


def _apply_document_filters(queryset, query_params):
    for field in TEXT_FILTER_FIELDS:
        value = str(query_params.get(field, "")).strip()
        if value:
            queryset = queryset.filter(
                **{f"{FILTER_FIELD_LOOKUPS.get(field, field)}__icontains": value[:200]}
            )
    for field in SELECT_FILTER_FIELDS:
        values = [str(value).strip() for value in query_params.getlist(field) if str(value).strip()]
        if values:
            queryset = queryset.filter(**{f"{field}__in": values[:100]})
    archived_filter = query_params.get("is_archived")
    if archived_filter is not None:
        queryset = queryset.filter(is_archived=_parse_query_boolean(archived_filter, "is_archived"))
    date_field = serializers.DateField()
    for field in DATE_FILTER_FIELDS:
        for suffix, lookup_suffix in DATE_FILTER_SUFFIXES.items():
            key = f"{field}{suffix}"
            raw_value = query_params.get(key)
            if raw_value in (None, ""):
                continue
            value = date_field.run_validation(raw_value)
            lookup = f"{field}{lookup_suffix}"
            if suffix == "__not":
                queryset = queryset.exclude(**{lookup: value})
            else:
                queryset = queryset.filter(**{lookup: value})
    return queryset


def _apply_document_ordering(queryset, raw_ordering):
    if not raw_ordering:
        return queryset
    descending = str(raw_ordering).startswith("-")
    field = str(raw_ordering)[1:] if descending else str(raw_ordering)
    lookup = ORDERING_FIELDS.get(field)
    if lookup is None:
        raise serializers.ValidationError({"ordering": "Select a supported ordering field."})
    prefix = "-" if descending else ""
    return queryset.order_by(f"{prefix}{lookup}", "id")


def _parse_query_boolean(value, field):
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise serializers.ValidationError({field: "Use true or false."})


def _doors_import_job(request, job_id):
    job = get_object_or_404(
        Job,
        pk=job_id,
        owner=request.user,
        kind="doors.run_dxl",
    )
    if job.status != JobStatus.SUCCEEDED:
        raise serializers.ValidationError(
            {"job_id": "The DOORS export job has not completed successfully."},
            code="DOORS_IMPORT_JOB_NOT_READY",
        )
    return job


def _field_capabilities(field):
    public_field = "cover_page_no" if field == "cover_page" else field
    if public_field in DATE_FILTER_FIELDS:
        filter_kind = "date"
    elif public_field in SELECT_FILTER_FIELDS:
        filter_kind = "select"
    elif public_field == "is_archived":
        filter_kind = "boolean"
    elif public_field in TEXT_FILTER_FIELDS:
        filter_kind = "text"
    else:
        filter_kind = "none"
    choices = []
    option_source = "panels" if field == "panel" else None
    if field == "status":
        choices = [{"value": value, "label": label} for value, label in ComplianceDocument._meta.get_field("status").choices]
    elif field == "cat":
        choices = [{"value": value, "label": label} for value, label in ComplianceDocument._meta.get_field("cat").choices]
    return {
        "filter_kind": filter_kind,
        "sortable": public_field in ORDERING_FIELDS,
        "choices": choices,
        "option_source": option_source,
    }


def _empty_tracking_payload():
    return {
        "responsible_mode": TrackingProfile.ResponsibleMode.AUTOMATIC,
        "responsible_person_ids": [],
        "notification_enabled": False,
        "notification_events": [],
        "docproof_issue": "",
        "docproof_status": "never_checked",
        "docproof_checked_at": None,
        "notification_checked_at": None,
        "version": 0,
        "updated_at": None,
    }


def _work_payload(document):
    return {
        "owner": document.owner_id,
        "owner_username": getattr(document.owner, "username", ""),
        "owner_group": document.owner_group_id,
        "owner_group_name": getattr(document.owner_group, "name", ""),
        "next_action_due_date": document.next_action_due_date,
        "version": document.version,
    }


def _notification_policy_payload(policy, *, can_manage=False):
    if policy is None:
        return {
            "version": 0,
            "event_rules": {},
            "change_note": "",
            "updated_at": None,
            "allowed_actions": {"manage": can_manage},
        }
    return {
        "version": policy.version,
        "event_rules": policy.event_rules,
        "change_note": policy.change_note,
        "updated_by": policy.updated_by_username,
        "updated_at": policy.created_at,
        "allowed_actions": {"manage": can_manage},
    }
