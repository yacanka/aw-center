"""Owner-safe HTTP serializers for ECR workflows."""

import json

from rest_framework import serializers

from integrations.jira.contracts import normalize_project_key, validate_extra_fields
from jobs.models import JobStatus
from orgs.models import Project
from projects.registry import get_project_definitions_by_capability

from .ecr_access import OPERATOR, PUBLISHER, has_ecr_role
from .models import EcrWorkflow, EcrWorkflowEvent, EcrWorkflowStatus

MAX_ECR_PROJECTS = 8
MAX_ECR_SUBTASKS = 20
DCC_PROJECT_SLUGS = frozenset(
    definition.slug for definition in get_project_definitions_by_capability("dcc")
)


class EcrCreateSerializer(serializers.Serializer):
    project_slugs = serializers.ListField(
        child=serializers.SlugField(max_length=64),
        allow_empty=False,
        max_length=MAX_ECR_PROJECTS,
    )

    def validate_project_slugs(self, values):
        if len(set(values)) != len(values):
            raise serializers.ValidationError("Project slugs must be unique.")
        if any(value not in DCC_PROJECT_SLUGS for value in values):
            raise serializers.ValidationError("Select only projects with DCC capability.")
        projects = list(
            Project.objects.filter(enabled=True, slug__in=values).order_by("slug")
        )
        if {project.slug for project in projects} != set(values):
            raise serializers.ValidationError("Select only enabled projects.")
        return projects


class EcrSubtaskSerializer(serializers.Serializer):
    summary = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=5000,
        trim_whitespace=True,
    )
    assignee = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
        trim_whitespace=True,
    )
    priority = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=50,
        trim_whitespace=True,
    )
    due_date = serializers.DateField(required=False, allow_null=True, default=None)


class EcrApprovalSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    project_key = serializers.CharField(max_length=20)
    extra_fields = serializers.JSONField(required=False, default=dict)
    subtasks = EcrSubtaskSerializer(
        many=True,
        required=False,
        default=list,
        allow_empty=True,
        max_length=MAX_ECR_SUBTASKS,
    )

    def validate_project_key(self, value):
        return normalize_project_key(value)

    def validate_extra_fields(self, value):
        protected = {"project", "summary", "description", "issuetype", "labels"}
        normalized = validate_extra_fields(value)
        if protected.intersection(normalized):
            raise serializers.ValidationError(
                "Base JIRA fields are controlled by the ECR workflow."
            )
        return normalized


class EcrVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class EcrWorkflowEventSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source="event_type")

    class Meta:
        model = EcrWorkflowEvent
        fields = ["type", "version", "code", "created_at"]


class EcrWorkflowSerializer(serializers.ModelSerializer):
    project_slugs = serializers.SlugRelatedField(
        source="projects",
        many=True,
        read_only=True,
        slug_field="slug",
    )
    approval = serializers.SerializerMethodField()
    publication = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = EcrWorkflow
        fields = [
            "id",
            "status",
            "version",
            "project_slugs",
            "snapshot",
            "approval",
            "publication",
            "allowed_actions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_approval(self, workflow):
        return {
            "project_key": workflow.project_key,
            "extra_fields": workflow.extra_fields,
            "subtasks": normalized_public_subtasks(workflow.selected_subtasks),
            "approved_at": workflow.approved_at,
            "rejected_at": workflow.rejected_at,
        }

    def get_publication(self, workflow):
        state = workflow.publication_state or {}
        job = workflow.publication_job
        subtask_keys = state.get("subtask_keys")
        confirmed = len(subtask_keys) if isinstance(subtask_keys, dict) else 0
        last_error = None
        if workflow.last_error_code:
            last_error = {
                "code": workflow.last_error_code,
                "detail": workflow.last_error_message,
            }
        return {
            "job_id": str(job.id) if job else None,
            "job_status": job.status if job else None,
            "jira_issue_key": workflow.jira_issue_key,
            "attachment_confirmed": bool(state.get("attachment_confirmed")),
            "subtasks_confirmed": confirmed,
            "subtasks_total": len(workflow.selected_subtasks or ()),
            "published_at": workflow.published_at,
            "last_error": last_error,
        }

    def get_allowed_actions(self, workflow):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        operator = has_ecr_role(actor, workflow, OPERATOR)
        publisher = has_ecr_role(actor, workflow, PUBLISHER)
        job = workflow.publication_job
        can_cancel = bool(
            publisher
            and workflow.status == EcrWorkflowStatus.PUBLISHING
            and job
            and job.status in {JobStatus.QUEUED, JobStatus.RUNNING}
        )
        return {
            "approve": operator and workflow.status == EcrWorkflowStatus.REVIEW,
            "reject": operator and workflow.status == EcrWorkflowStatus.REVIEW,
            "publish": publisher and workflow.status == EcrWorkflowStatus.APPROVED,
            "resume": publisher
            and workflow.status
            in {
                EcrWorkflowStatus.FAILED,
                EcrWorkflowStatus.CANCELLED,
                EcrWorkflowStatus.RECONCILIATION_REQUIRED,
            },
            "cancel": can_cancel,
        }


class EcrWorkflowDetailSerializer(EcrWorkflowSerializer):
    events = serializers.SerializerMethodField()

    class Meta(EcrWorkflowSerializer.Meta):
        fields = [*EcrWorkflowSerializer.Meta.fields, "events"]

    def get_events(self, workflow):
        events = list(workflow.events.order_by("-created_at", "-id")[:100])
        return EcrWorkflowEventSerializer(reversed(events), many=True).data


def normalized_public_subtasks(values):
    """Keep the stable public subtask shape even for empty optional values."""

    result = []
    for value in values or ():
        if not isinstance(value, dict):
            continue
        result.append(
            {
                "summary": str(value.get("summary") or ""),
                "description": str(value.get("description") or ""),
                "assignee": str(value.get("assignee") or ""),
                "priority": str(value.get("priority") or ""),
                "due_date": value.get("due_date") or None,
            }
        )
    return result


def parse_project_slugs(data) -> list[str]:
    """Accept a JSON array string and repeated multipart values."""

    getlist = getattr(data, "getlist", None)
    values = getlist("project_slugs") if getlist else [data.get("project_slugs")]
    values = [value for value in values if value not in (None, "")]
    if len(values) == 1 and isinstance(values[0], str):
        try:
            decoded = json.loads(values[0])
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            values = decoded
    return values
