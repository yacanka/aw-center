"""Authenticated saved-list resource, without upstream JIRA side effects."""

from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .user_content import get_saved_lists, replace_saved_lists


class SavedListsSerializer(serializers.Serializer):
    lists = serializers.JSONField()
    version = serializers.IntegerField(min_value=0)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != {"lists", "version"} or isinstance(data.get("version"), bool):
            raise serializers.ValidationError({"non_field_errors": ["Provide only lists and an integer version."]})
        return super().to_internal_value(data)


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def saved_lists(request):
    if request.method == "GET":
        return Response(get_saved_lists(request.user))
    serializer = SavedListsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    return Response(replace_saved_lists(request.user, values["lists"], version=values["version"]))
