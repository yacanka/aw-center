"""API serializers for project-scoped JIRA issue drafts."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from integrations.jira.contracts import normalize_project_key, validate_extra_fields
from orgs.models import Project
from projects.registry import get_project_definitions_by_capability

from .issue_draft_models import (
    JiraIssueDraft,
    JiraIssueDraftEvent,
    JiraIssueDraftStatus,
)
from .access_policy import OPERATOR, PUBLISHER, has_resource_role
from .services.jira_links import build_jira_issue_url

DCC_PROJECT_SLUGS = tuple(
    definition.slug for definition in get_project_definitions_by_capability("dcc")
)


class JiraIssueDraftEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = JiraIssueDraftEvent
        fields = ["id", "event_type", "version", "details", "created_at"]


class JiraIssueDraftSerializer(serializers.ModelSerializer):
    events = serializers.SerializerMethodField()
    jira_issue_url = serializers.SerializerMethodField()
    project_slugs = serializers.SlugRelatedField(
        source="projects",
        many=True,
        read_only=True,
        slug_field="slug",
    )
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = JiraIssueDraft
        fields = [
            "id",
            "owner",
            "assigned_users",
            "project_slugs",
            "source_job",
            "publication_job",
            "project_key",
            "summary",
            "description",
            "status",
            "version",
            "extra_fields",
            "jira_issue_key",
            "jira_issue_url",
            "approved_at",
            "published_at",
            "last_error_code",
            "last_error_message",
            "created_at",
            "updated_at",
            "events",
            "allowed_actions",
        ]
        read_only_fields = fields

    def get_events(self, draft):
        events = list(draft.events.order_by("-created_at", "-id")[:100])
        return JiraIssueDraftEventSerializer(reversed(events), many=True).data

    def get_jira_issue_url(self, draft):
        return build_jira_issue_url(draft.jira_issue_key) if draft.jira_issue_key else None

    def get_allowed_actions(self, draft):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if not actor or not actor.is_authenticated:
            return empty_actions()
        operator = has_resource_role(actor, draft, OPERATOR)
        publisher = has_resource_role(actor, draft, PUBLISHER)
        status = draft.status
        return {
            "edit": operator
            and status
            not in {
                JiraIssueDraftStatus.PUBLISHING,
                JiraIssueDraftStatus.PUBLISHED,
                JiraIssueDraftStatus.RECONCILIATION_REQUIRED,
            },
            "approve": operator and status == JiraIssueDraftStatus.DRAFT,
            "preflight": publisher
            and status
            not in {JiraIssueDraftStatus.PUBLISHING, JiraIssueDraftStatus.PUBLISHED},
            "publish": publisher
            and (
                status == JiraIssueDraftStatus.RECONCILIATION_REQUIRED
                or status in {JiraIssueDraftStatus.APPROVED, JiraIssueDraftStatus.FAILED}
                and bool(draft.approved_at)
            ),
        }


class JiraIssueDraftCreateSerializer(serializers.Serializer):
    source_job_id = serializers.UUIDField()
    project_key = serializers.CharField(required=False, allow_blank=True, max_length=20)
    project_slugs = serializers.SlugRelatedField(
        source="projects",
        queryset=Project.objects.filter(enabled=True, slug__in=DCC_PROJECT_SLUGS),
        slug_field="slug",
        many=True,
        allow_empty=False,
    )
    assigned_users = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(),
        many=True,
        required=False,
        default=list,
    )

    def validate_project_key(self, value):
        return normalize_project_key(value) if value else value

    def validate_project_slugs(self, value):
        return unique_projects(value)


class JiraIssueDraftUpdateSerializer(serializers.Serializer):
    project_key = serializers.CharField(max_length=20, required=False)
    summary = serializers.CharField(
        min_length=1, max_length=255, trim_whitespace=True, required=False
    )
    description = serializers.CharField(
        min_length=1, max_length=30000, trim_whitespace=True, required=False
    )
    extra_fields = serializers.JSONField(required=False)
    assigned_users = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(),
        many=True,
        required=False,
    )
    project_slugs = serializers.SlugRelatedField(
        source="projects",
        queryset=Project.objects.filter(enabled=True, slug__in=DCC_PROJECT_SLUGS),
        slug_field="slug",
        many=True,
        allow_empty=False,
        required=False,
    )
    version = serializers.IntegerField(min_value=1)

    def validate(self, attributes):
        if not any(key != "version" for key in attributes):
            raise serializers.ValidationError("Provide at least one draft field to update.")
        return attributes

    def validate_project_key(self, value):
        return normalize_project_key(value)

    def validate_extra_fields(self, value):
        return validate_extra_fields(value)

    def validate_project_slugs(self, value):
        return unique_projects(value)


class JiraIssueDraftVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class JiraIssueDraftPublishSerializer(JiraIssueDraftVersionSerializer):
    reconcile = serializers.BooleanField(required=False, default=False)


class JiraIssueDraftPreflightSerializer(JiraIssueDraftVersionSerializer):
    pass


def unique_projects(projects):
    if len({project.pk for project in projects}) != len(projects):
        raise serializers.ValidationError("Project slugs must be unique.")
    return projects


def empty_actions():
    return {"edit": False, "approve": False, "preflight": False, "publish": False}
