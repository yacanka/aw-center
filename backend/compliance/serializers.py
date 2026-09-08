"""Concrete serializers for the canonical compliance aggregate."""

import re

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from orgs.access_policy import has_project_role
from orgs.models import Panel, Person, ProjectRoleAssignment

from .notifications import SUPPORTED_EVENTS

from .models import (
    ComplianceDocument,
    CoverPage,
    ImportAudit,
    ReviewTask,
    TrackingProfile,
    WorkflowEvent,
)


CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
LINE_BREAKS = re.compile(r"[\r\n]")
SINGLE_LINE_FIELDS = frozenset(
    {
        "name",
        "tech_doc_no",
        "tech_doc_issue",
        "delivered_tech_doc_issue",
        "tech_doc_no_2",
        "tech_doc_issue_2",
        "delivered_tech_doc_issue_2",
        "responsible",
        "path",
    }
)


def tracking_responsible_options(document):
    if document is None or not document.panel_id:
        return []
    people = (
        Person.objects.filter(responsible_assignments__panel_id=document.panel_id)
        .exclude(email="")
        .order_by("name", "person_id")
        .distinct()
    )
    return [
        {
            "id": person.pk,
            "name": person.name,
            "email": person.email,
        }
        for person in people
    ]


class CoverPageSerializer(serializers.ModelSerializer):
    number = serializers.CharField(
        max_length=32,
        allow_blank=True,
        required=True,
        trim_whitespace=True,
    )
    issue = serializers.CharField(
        max_length=255,
        allow_blank=True,
        allow_null=True,
        required=False,
    )
    version = serializers.IntegerField(min_value=1, required=False)

    class Meta:
        model = CoverPage
        fields = ("id", "number", "issue", "version")
        read_only_fields = ("id",)

    def validate(self, attributes):
        invalid = [
            field
            for field in ("number", "issue")
            if isinstance(attributes.get(field), str)
            and (
                CONTROL_CHARACTERS.search(attributes[field])
                or LINE_BREAKS.search(attributes[field])
            )
        ]
        if invalid:
            raise serializers.ValidationError(
                {field: "Control characters are not allowed." for field in invalid}
            )
        return attributes


class CoverPageVersionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "COVER_PAGE_VERSION_CONFLICT"
    default_detail = "This cover page changed after you opened it."


class ComplianceDocumentSerializer(serializers.ModelSerializer):
    project_slug = serializers.CharField(source="project.slug", read_only=True)
    panel_name = serializers.CharField(source="panel.name", read_only=True, allow_null=True)
    ata = serializers.CharField(source="panel.ata", read_only=True, allow_null=True)
    cover_page = CoverPageSerializer()
    panel = serializers.PrimaryKeyRelatedField(
        queryset=Panel.objects.none(),
        allow_null=True,
        required=False,
    )
    change_reason = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=100,
    )

    class Meta:
        model = ComplianceDocument
        fields = (
            "id",
            "project_slug",
            "panel",
            "panel_name",
            "ata",
            "cover_page",
            "name",
            "signature_panel",
            "tech_doc_no",
            "tech_doc_issue",
            "delivered_tech_doc_issue",
            "tech_doc_no_2",
            "tech_doc_issue_2",
            "delivered_tech_doc_issue_2",
            "responsible",
            "cat",
            "moc",
            "mom_no",
            "requirements",
            "status",
            "ubm_target_date",
            "ubm_delivery_date",
            "path",
            "notes",
            "owner",
            "owner_group",
            "next_action_due_date",
            "is_archived",
            "archived_at",
            "archived_by",
            "archive_reason",
            "version",
            "created_at",
            "updated_at",
            "change_reason",
        )
        read_only_fields = (
            "status",
            "ubm_target_date",
            "ubm_delivery_date",
            "owner",
            "owner_group",
            "next_action_due_date",
            "is_archived",
            "archived_at",
            "archived_by",
            "archive_reason",
            "version",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project = self.context.get("project")
        if project is not None:
            self.fields["panel"].queryset = Panel.objects.filter(project=project)

    def validate_panel(self, panel):
        project = self.context.get("project")
        if panel is not None and (project is None or panel.project_id != project.pk):
            raise serializers.ValidationError("Panel must belong to the URL project.")
        return panel

    def validate(self, attributes):
        project = self.context.get("project")
        if project is None:
            raise serializers.ValidationError("Project context is required.")
        cover_page = attributes.get("cover_page")
        if cover_page is not None and "number" not in cover_page:
            raise serializers.ValidationError(
                {"cover_page": {"number": "This field is required."}}
            )
        attributes.pop("change_reason", None)
        self._normalize_lists(attributes)
        self._reject_control_characters(attributes)
        notes = attributes.get("notes")
        if notes is not None and len(notes) > 5000:
            raise serializers.ValidationError({"notes": "Use at most 5000 characters."})
        return attributes

    @staticmethod
    def _normalize_lists(attributes):
        for field in ("requirements", "signature_panel"):
            if field not in attributes:
                continue
            values = attributes[field] or []
            if not isinstance(values, list) or len(values) > 100:
                raise serializers.ValidationError({field: "Use a list with at most 100 values."})
            cleaned = []
            for value in values:
                text = str(value).strip()
                if CONTROL_CHARACTERS.search(text) or LINE_BREAKS.search(text):
                    raise serializers.ValidationError(
                        {field: "Control characters are not allowed."}
                    )
                if len(text) > 256:
                    raise serializers.ValidationError(
                        {field: "Each value must contain at most 256 characters."}
                    )
                if text and text not in cleaned:
                    cleaned.append(text)
            attributes[field] = cleaned

    @staticmethod
    def _reject_control_characters(attributes):
        invalid_controls = [
            field
            for field, value in attributes.items()
            if isinstance(value, str) and CONTROL_CHARACTERS.search(value)
        ]
        invalid_lines = [
            field
            for field in SINGLE_LINE_FIELDS
            if isinstance(attributes.get(field), str)
            and LINE_BREAKS.search(attributes[field])
        ]
        invalid = set(invalid_controls + invalid_lines)
        if invalid:
            raise serializers.ValidationError(
                {field: "Control characters are not allowed." for field in invalid}
            )

    def _resolve_cover_page(self, data):
        number = str(data.get("number", "")).strip()
        issue_provided = "issue" in data
        issue = data.get("issue")
        if not number:
            if self.instance is not None and not self.instance.cover_page.number:
                cover_page = self.instance.cover_page
                if issue_provided and cover_page.issue != issue:
                    if data.get("version") != cover_page.version:
                        raise CoverPageVersionConflict()
                    cover_page.issue = issue
                    cover_page.version += 1
                    cover_page._history_user = self.context["request"].user
                    cover_page.save(update_fields=["issue", "version"])
                return cover_page
            return CoverPage.objects.create(
                project=self.context["project"],
                number="",
                issue=issue,
            )
        expected_version = data.get("version")
        cover_page = CoverPage.objects.select_for_update().filter(
            project=self.context["project"],
            number=number,
        ).first()
        if cover_page is None:
            return CoverPage.objects.create(
                project=self.context["project"],
                number=number,
                issue=issue,
            )
        if self.instance is None and expected_version is None and issue in (None, ""):
            return cover_page
        if issue_provided and cover_page.issue != issue:
            if expected_version != cover_page.version:
                raise CoverPageVersionConflict()
            cover_page.issue = issue
            cover_page.version += 1
            cover_page._history_user = self.context["request"].user
            cover_page.save(update_fields=["issue", "version"])
        return cover_page

    @transaction.atomic
    def create(self, validated_data):
        cover_page = self._resolve_cover_page(validated_data.pop("cover_page"))
        document = ComplianceDocument(
            **validated_data,
            project=self.context["project"],
            cover_page=cover_page,
            owner=self.context["request"].user,
        )
        document.full_clean()
        document._history_user = self.context["request"].user
        document.save()
        return document

    @transaction.atomic
    def update(self, instance, validated_data):
        cover_page_data = validated_data.pop("cover_page", None)
        if cover_page_data is not None:
            instance.cover_page = self._resolve_cover_page(cover_page_data)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance._history_user = self.context["request"].user
        instance._change_reason = str(self.initial_data.get("change_reason", "")).strip()[:100]
        instance.save()
        return instance


class WorkflowEventSerializer(serializers.ModelSerializer):
    actor = serializers.StringRelatedField()

    class Meta:
        model = WorkflowEvent
        fields = (
            "id",
            "sequence",
            "previous_status",
            "status",
            "effective_date",
            "next_action_due_date",
            "reason",
            "source",
            "actor",
            "created_at",
        )


class ReviewTaskSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = ReviewTask
        fields = (
            "id",
            "kind",
            "status",
            "assignee",
            "assignee_username",
            "requested_by_username",
            "decided_by_username",
            "due_date",
            "request_note",
            "decision_note",
            "source_version",
            "created_at",
            "decided_at",
            "allowed_actions",
        )
        read_only_fields = fields

    def get_allowed_actions(self, task):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        project = self.context.get("project") or task.document.project
        if not user or not user.is_authenticated or task.status != ReviewTask.Status.PENDING:
            return {"approve": False, "request_changes": False, "cancel": False}
        is_current = not task.document.is_archived and task.source_version == task.document.version
        is_manager = has_project_role(
            user,
            project,
            ProjectRoleAssignment.Domain.COMPLIANCE,
            ProjectRoleAssignment.Role.MANAGER,
        )
        can_decide = is_current and (task.assignee_id == user.pk or is_manager)
        return {
            "approve": can_decide,
            "request_changes": can_decide,
            "cancel": is_current and is_manager,
        }


class TrackingProfileSerializer(serializers.ModelSerializer):
    responsible_person_ids = serializers.PrimaryKeyRelatedField(
        source="responsible_people",
        queryset=Person.objects.all(),
        many=True,
        required=False,
    )
    responsible_options = serializers.SerializerMethodField()

    class Meta:
        model = TrackingProfile
        fields = (
            "responsible_mode",
            "responsible_person_ids",
            "responsible_options",
            "notification_enabled",
            "notification_events",
            "docproof_issue",
            "docproof_status",
            "docproof_checked_at",
            "notification_checked_at",
            "version",
            "updated_at",
        )
        read_only_fields = (
            "docproof_issue",
            "docproof_status",
            "docproof_checked_at",
            "notification_checked_at",
            "version",
            "updated_at",
            "responsible_options",
        )

    def get_responsible_options(self, profile):
        document = profile.document if profile else self.context.get("document")
        return tracking_responsible_options(document)

    def validate_notification_events(self, values):
        events = list(dict.fromkeys(values or []))
        if len(events) > len(SUPPORTED_EVENTS) or not set(events).issubset(
            SUPPORTED_EVENTS
        ):
            raise serializers.ValidationError("Select only supported notification events.")
        return events

    def validate_responsible_person_ids(self, values):
        if len(values) > 100:
            raise serializers.ValidationError("Use a list with at most 100 person IDs.")
        return list({person.pk: person for person in values}.values())

    def validate(self, attributes):
        profile = self.instance
        document = profile.document if profile else self.context.get("document")
        mode = attributes.get(
            "responsible_mode",
            getattr(profile, "responsible_mode", TrackingProfile.ResponsibleMode.AUTOMATIC),
        )
        responsible_people = attributes.get("responsible_people")
        if responsible_people is None:
            responsible_people = (
                list(profile.responsible_people.all())
                if profile is not None and profile.pk
                else []
            )
        person_ids = {person.pk for person in responsible_people}
        enabled = attributes.get(
            "notification_enabled",
            getattr(profile, "notification_enabled", False),
        )
        events = attributes.get(
            "notification_events",
            getattr(profile, "notification_events", []),
        )
        if document is None:
            raise serializers.ValidationError("Document context is required.")
        allowed_ids = set(
            Person.objects.filter(
                responsible_assignments__panel_id=document.panel_id,
            ).exclude(email="").values_list("pk", flat=True)
        ) if document.panel_id else set()
        if mode == TrackingProfile.ResponsibleMode.CUSTOM and not person_ids.issubset(allowed_ids):
            raise serializers.ValidationError(
                {"responsible_person_ids": "Select people assigned to the document panel."}
            )
        if enabled:
            has_recipients = (
                bool(allowed_ids)
                if mode == TrackingProfile.ResponsibleMode.AUTOMATIC
                else bool(person_ids)
            )
            if not has_recipients:
                raise serializers.ValidationError(
                    {"responsible_person_ids": "Assign at least one panel responsible before enabling notifications."}
                )
            if not events:
                raise serializers.ValidationError(
                    {"notification_events": "Select at least one notification event."}
                )
        return attributes


class ImportAuditSerializer(serializers.ModelSerializer):
    imported_by_username = serializers.SerializerMethodField()

    class Meta:
        model = ImportAudit
        fields = (
            "id",
            "project",
            "source_filename",
            "source_size",
            "source_sha256",
            "imported_by",
            "imported_by_username",
            "request_id",
            "header_row",
            "mapped_columns",
            "unmapped_columns",
            "missing_columns",
            "total_rows",
            "created_count",
            "updated_count",
            "unchanged_count",
            "rejected_count",
            "error_summary",
            "status",
            "started_at",
            "completed_at",
            "duration_ms",
        )
        read_only_fields = fields

    def get_imported_by_username(self, audit):
        return getattr(audit.imported_by, "username", "")
