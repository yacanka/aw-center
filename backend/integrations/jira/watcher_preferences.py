"""User-bound Watcher display preferences in the existing preferences store."""

from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from orgs.models import Project
from users.models import get_user_preferences
from .access_policy import VIEWER, require_projects_role, project_records_for_user
from .record_serializers import JIRA_PROJECT_SLUGS
from .watcher_fields import MAX_DETAIL_FIELDS, is_detail_field_id
from .preferences import normalize_jira_preferences, update_jira_preferences




class WatcherPreferencesSerializer(serializers.Serializer):
    outstanding_only = serializers.BooleanField(required=False)
    project_slug = serializers.ChoiceField(choices=JIRA_PROJECT_SLUGS, required=False)
    component_name = serializers.CharField(max_length=255, allow_null=True, required=False)
    record_id = serializers.UUIDField(required=False)
    detail_field_ids = serializers.ListField(
        child=serializers.CharField(max_length=64), max_length=MAX_DETAIL_FIELDS, required=False)

    def validate(self, values):
        component_selection = "component_name" in values
        if component_selection != ("record_id" in values):
            raise serializers.ValidationError("Select a tracked component and record together.")
        if component_selection and "project_slug" in values:
            raise serializers.ValidationError("Select one detail field scope.")
        if (component_selection or "project_slug" in values) != ("detail_field_ids" in values):
            raise serializers.ValidationError("Select a scope and its detail fields together.")
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
    if "component_name" in values:
        record = get_object_or_404(project_records_for_user(request.user), pk=values["record_id"])
        name = values["component_name"]
        matches = record.components == [] if name is None else name in (record.components or [])
        if not matches:
            raise serializers.ValidationError("No tracked issue has the selected component. Reload components.")
    if "project_slug" in values:
        projects = list(Project.objects.filter(slug=values["project_slug"], enabled=True))
        require_projects_role(request.user, projects, VIEWER)
    return Response(update_jira_preferences(request.user, values))
