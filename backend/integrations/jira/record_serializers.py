"""Canonical DCC record serializers."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from orgs.models import Project
from projects.registry import get_project_definitions_by_capability

from .workflow_models import JiraTrackedIssue
from .services.jira_links import build_jira_issue_url

JIRA_PROJECT_SLUGS = tuple(
    definition.slug for definition in get_project_definitions_by_capability("jira")
)


class JiraTrackedIssueFilterSerializer(serializers.Serializer):
    issue = serializers.CharField(required=False, max_length=64)
    title = serializers.CharField(required=False, max_length=255)
    project_slug = serializers.ChoiceField(choices=JIRA_PROJECT_SLUGS, required=False)


class JiraTrackedIssueSerializer(serializers.ModelSerializer):
    jira_issue_url = serializers.SerializerMethodField()
    project_slugs = serializers.SlugRelatedField(
        source="projects",
        many=True,
        read_only=True,
        slug_field="slug",
    )

    class Meta:
        model = JiraTrackedIssue
        fields = [
            "id",
            "issue",
            "jira_issue_url",
            "title",
            "owner",
            "assigned_users",
            "project_slugs",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_jira_issue_url(self, instance):
        return build_jira_issue_url(instance.issue)


class JiraTrackedIssueMutationSerializer(serializers.Serializer):
    issue = serializers.RegexField(
        r"^[A-Z][A-Z0-9_]{1,19}-[1-9][0-9]*$",
        max_length=64,
    )
    title = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    assigned_users = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(),
        many=True,
        required=False,
        default=list,
    )
    project_slugs = serializers.SlugRelatedField(
        source="projects",
        queryset=Project.objects.filter(enabled=True, slug__in=JIRA_PROJECT_SLUGS),
        slug_field="slug",
        many=True,
        allow_empty=False,
    )

    def validate_project_slugs(self, value):
        return unique_projects(value)


class JiraTrackedIssueUpdateSerializer(serializers.Serializer):
    issue = serializers.RegexField(
        r"^[A-Z][A-Z0-9_]{1,19}-[1-9][0-9]*$",
        max_length=64,
        required=False,
    )
    assigned_users = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(),
        many=True,
        required=False,
    )
    project_slugs = serializers.SlugRelatedField(
        source="projects",
        queryset=Project.objects.filter(enabled=True, slug__in=JIRA_PROJECT_SLUGS),
        slug_field="slug",
        many=True,
        allow_empty=False,
        required=False,
    )
    version = serializers.IntegerField(min_value=1)

    def validate(self, values):
        if "title" in self.initial_data or "active" in self.initial_data:
            raise serializers.ValidationError("The title is supplied by JIRA; tracking is always enabled.")
        return values

    def validate_project_slugs(self, value):
        return unique_projects(value)


class JiraTrackedIssueDeleteSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


def unique_projects(projects):
    if len({project.pk for project in projects}) != len(projects):
        raise serializers.ValidationError("Project slugs must be unique.")
    return projects
