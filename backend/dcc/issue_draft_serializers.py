"""API serializers for owned JIRA issue drafts and content-free audit events."""

from django.conf import settings
from rest_framework import serializers

from .issue_draft_contracts import normalize_project_key, validate_extra_fields
from .issue_draft_models import JiraIssueDraft, JiraIssueDraftEvent


class JiraIssueDraftEventSerializer(serializers.ModelSerializer):
    """Serialize immutable lifecycle metadata without actor identity or draft content."""

    class Meta:
        model = JiraIssueDraftEvent
        fields = ["id", "event_type", "version", "details", "created_at"]


class JiraIssueDraftSerializer(serializers.ModelSerializer):
    """Serialize the owner-visible review and publication state."""

    events = serializers.SerializerMethodField()
    jira_issue_url = serializers.SerializerMethodField()

    class Meta:
        model = JiraIssueDraft
        fields = [
            "id", "source_job", "project_key", "summary", "description", "status", "version",
            "extra_fields", "jira_issue_key", "jira_issue_url", "approved_at", "published_at", "last_error_code",
            "last_error_message", "created_at", "updated_at", "events",
        ]

    def get_events(self, draft):
        """Return at most the latest one hundred audit events chronologically."""

        events = list(draft.events.order_by("-created_at", "-id")[:100])
        return JiraIssueDraftEventSerializer(reversed(events), many=True).data

    def get_jira_issue_url(self, draft):
        """Return a configured link only after a confirmed publication."""

        if not draft.jira_issue_key:
            return None
        return f"{settings.JIRA_URL.rstrip('/')}/browse/{draft.jira_issue_key}"


class JiraIssueDraftCreateSerializer(serializers.Serializer):
    """Validate draft creation from one owner-scoped analysis job."""

    source_job_id = serializers.UUIDField()
    project_key = serializers.CharField(required=False, allow_blank=True, max_length=20)

    def validate_project_key(self, value):
        """Normalize an explicit project key when supplied."""

        return normalize_project_key(value) if value else value


class JiraIssueDraftUpdateSerializer(serializers.Serializer):
    """Validate a complete optimistic-concurrency draft edit."""

    project_key = serializers.CharField(max_length=20)
    summary = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    description = serializers.CharField(min_length=1, max_length=30000, trim_whitespace=True)
    extra_fields = serializers.JSONField(required=False, default=dict)
    version = serializers.IntegerField(min_value=1)

    def validate_project_key(self, value):
        """Normalize and validate the target JIRA project."""

        return normalize_project_key(value)

    def validate_extra_fields(self, value):
        """Accept only bounded primitive values; live metadata is checked before publish."""

        return validate_extra_fields(value)


class JiraIssueDraftVersionSerializer(serializers.Serializer):
    """Validate a lifecycle decision against a known draft version."""

    version = serializers.IntegerField(min_value=1)


class JiraIssueDraftPublishSerializer(JiraIssueDraftVersionSerializer):
    """Validate a transient JIRA session used only for this publication call."""

    JSESSIONID = serializers.CharField(write_only=True, min_length=8, max_length=4096, trim_whitespace=True)


class JiraIssueDraftPreflightSerializer(serializers.Serializer):
    """Validate a transient JIRA session used only for create-contract inspection."""

    JSESSIONID = serializers.CharField(write_only=True, min_length=8, max_length=4096, trim_whitespace=True)
