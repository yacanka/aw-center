"""Request and response contracts for Watcher reminder delivery."""

from rest_framework import serializers

from .workflow_models import JiraReminderDelivery


class DccReminderCreateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    ccb_no = serializers.IntegerField(min_value=1, max_value=999999)
    due_date = serializers.DateField()


class JiraReminderDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = JiraReminderDelivery
        fields = (
            "id",
            "status",
            "recipient_count",
            "error_code",
            "created_at",
            "sent_at",
        )
        read_only_fields = fields
