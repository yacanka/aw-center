"""Permission-protected project notification-policy API."""

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.api_errors import error_response
from common.compdoc_notification_policy import (
    PolicyVersionConflict,
    policy_payload,
    save_policy,
)
from common.compdoc_permissions import StrictDjangoModelPermissions
from common.models import Titles

MANAGE_PERMISSION = "common.manage_compdoc_notification_policy"


class EventRuleSerializer(serializers.Serializer):
    """Validate cadence and recipient tiers for one event."""

    reminder_interval_hours = serializers.IntegerField(min_value=0, max_value=8760)
    failure_retry_hours = serializers.IntegerField(min_value=1, max_value=720)
    primary_titles = serializers.ListField(
        child=serializers.ChoiceField(choices=Titles.choices), allow_empty=True
    )
    escalation_titles = serializers.ListField(
        child=serializers.ChoiceField(choices=Titles.choices), allow_empty=True
    )
    escalate_after_hours = serializers.IntegerField(min_value=0, max_value=8760)

    def validate(self, attributes):
        """Reject ambiguous or duplicate recipient tiers."""

        primary = attributes["primary_titles"]
        escalation = attributes["escalation_titles"]
        if len(primary) != len(set(primary)) or len(escalation) != len(set(escalation)):
            raise serializers.ValidationError("Recipient roles must be unique.")
        if escalation and not primary:
            raise serializers.ValidationError("Choose primary roles before escalation roles.")
        if set(primary) & set(escalation):
            raise serializers.ValidationError("Primary and escalation roles must be different.")
        return attributes


class EventRulesSerializer(serializers.Serializer):
    """Validate every supported notification event explicitly."""

    overdue = EventRuleSerializer()
    due_soon = EventRuleSerializer()
    revision_available = EventRuleSerializer()


class NotificationPolicyUpdateSerializer(serializers.Serializer):
    """Validate an optimistic, auditable policy revision request."""

    expected_version = serializers.IntegerField(min_value=0)
    change_note = serializers.CharField(min_length=3, max_length=255, trim_whitespace=True)
    rules = EventRulesSerializer()


def compdoc_notification_policy_view_factory(model):
    """Create a project-bound policy read and revision endpoint."""

    class CompDocNotificationPolicyView(APIView):
        queryset = model.objects.none()
        permission_classes = [StrictDjangoModelPermissions]

        def get(self, request):
            return Response(_payload(model, request.user))

        def put(self, request):
            if not request.user.has_perm(MANAGE_PERMISSION):
                return _permission_error()
            serializer = NotificationPolicyUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            return _save_response(model, request.user, serializer.validated_data)

    return CompDocNotificationPolicyView


def _save_response(model, user, data):
    try:
        save_policy(
            model._meta.app_label,
            data["rules"],
            data["change_note"],
            data["expected_version"],
            user,
        )
    except PolicyVersionConflict:
        return error_response(
            "The notification policy changed. Reload it before saving.",
            code="COMPDOC_POLICY_VERSION_CONFLICT",
            response_status=status.HTTP_409_CONFLICT,
        )
    return Response(_payload(model, user))


def _payload(model, user):
    can_manage = user.has_perm(MANAGE_PERMISSION) and user.has_perm(
        f"{model._meta.app_label}.change_compdoc"
    )
    return policy_payload(model._meta.app_label, can_manage)


def _permission_error():
    return error_response(
        "You are not authorized to manage project notification policy.",
        code="COMPDOC_POLICY_PERMISSION_DENIED",
        response_status=status.HTTP_403_FORBIDDEN,
    )
