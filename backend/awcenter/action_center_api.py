"""Authenticated HTTP contract for the permission-aware Action Center."""

from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .action_center import available_items, build_action_center
from .action_center_decisions import record_attention_decision


class AttentionDecisionSerializer(serializers.Serializer):
    """Validate bounded attention item decisions."""

    item_id = serializers.RegexField(
        r"^(job|import):[0-9a-f-]{36}$|^invitation:[1-9][0-9]*$",
        max_length=100,
    )
    action = serializers.ChoiceField(choices=("snooze", "dismiss"))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def action_center(request):
    """Return the current user's bounded cross-workflow attention queue."""

    return Response(build_action_center(request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def action_center_decision(request):
    """Snooze or dismiss one currently authorized attention item."""

    serializer = AttentionDecisionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    item_id = serializer.validated_data["item_id"]
    if item_id not in {item["id"] for item in available_items(request.user)}:
        raise serializers.ValidationError(
            {"item_id": "This attention item is unavailable."},
            code="ATTENTION_ITEM_UNAVAILABLE",
        )
    record_attention_decision(request.user, item_id, serializer.validated_data["action"])
    return Response(status=status.HTTP_204_NO_CONTENT)
