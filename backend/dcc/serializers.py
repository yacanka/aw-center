"""Canonical DCC record serializers."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from orgs.models import Project
from projects.registry import get_project_definitions_by_capability

from .models import DccRecord
from .services.jira_links import build_jira_issue_url

DCC_PROJECT_SLUGS = tuple(
    definition.slug for definition in get_project_definitions_by_capability("dcc")
)


class DccRecordSerializer(serializers.ModelSerializer):
    jira_issue_url = serializers.SerializerMethodField()
    project_slugs = serializers.SlugRelatedField(
        source="projects",
        many=True,
        read_only=True,
        slug_field="slug",
    )

    class Meta:
        model = DccRecord
        fields = [
            "id",
            "issue",
            "jira_issue_url",
            "title",
            "active",
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


class DccRecordMutationSerializer(serializers.Serializer):
    issue = serializers.RegexField(
        r"^[A-Z][A-Z0-9_]{1,19}-[1-9][0-9]*$",
        max_length=64,
    )
    title = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    active = serializers.BooleanField(default=True)
    assigned_users = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(),
        many=True,
        required=False,
        default=list,
    )
    project_slugs = serializers.SlugRelatedField(
        source="projects",
        queryset=Project.objects.filter(enabled=True, slug__in=DCC_PROJECT_SLUGS),
        slug_field="slug",
        many=True,
        allow_empty=False,
    )

    def validate_project_slugs(self, value):
        return unique_projects(value)


class DccRecordUpdateSerializer(serializers.Serializer):
    issue = serializers.RegexField(
        r"^[A-Z][A-Z0-9_]{1,19}-[1-9][0-9]*$",
        max_length=64,
        required=False,
    )
    title = serializers.CharField(
        min_length=1,
        max_length=255,
        trim_whitespace=True,
        required=False,
    )
    active = serializers.BooleanField(required=False)
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

    def validate_project_slugs(self, value):
        return unique_projects(value)


class DccRecordDeleteSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


def unique_projects(projects):
    if len({project.pk for project in projects}) != len(projects):
        raise serializers.ValidationError("Project slugs must be unique.")
    return projects
