"""User-bound Watcher display preferences in the existing preferences store."""

from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orgs.models import Project
from users.models import get_user_preferences
from .access_policy import VIEWER, require_projects_role
from .record_serializers import JIRA_PROJECT_SLUGS
from .watcher_fields import MAX_DETAIL_FIELDS, is_detail_field_id
from .preferences import normalize_jira_preferences, update_jira_preferences




class WatcherPreferencesSerializer(serializers.Serializer):
    outstanding_only = serializers.BooleanField(required=False)
    project_slug = serializers.ChoiceField(choices=JIRA_PROJECT_SLUGS, required=False)
    detail_field_ids = serializers.ListField(
        child=serializers.CharField(max_length=64), max_length=MAX_DETAIL_FIELDS, required=False)

    def validate(self, values):
        if ("project_slug" in values) != ("detail_field_ids" in values):
            raise serializers.ValidationError("Select a project and its detail fields together.")
        if not values:
            raise serializers.ValidationError("Provide a Watcher preference.")
        if not all(is_detail_field_id(item) for item in values.get("detail_field_ids", [])):
            raise serializers.ValidationError("Select supported JIRA display fields.")
        return values


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def watcher_preferences(request):
    if request.method == "GET":
        return Response(normalize_jira_preferences(get_user_preferences(request.user).extra_settings))
    serializer = WatcherPreferencesSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    if "project_slug" in values:
        projects = list(Project.objects.filter(slug=values["project_slug"], enabled=True))
        require_projects_role(request.user, projects, VIEWER)
    return Response(update_jira_preferences(request.user, values))
