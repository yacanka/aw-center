"""Request and response contracts for Watcher reminder delivery."""

from rest_framework import serializers

from .models import DccReminderDelivery


class DccReminderCreateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    ccb_no = serializers.IntegerField(min_value=1, max_value=999999)
    due_date = serializers.DateField()


class DccReminderDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = DccReminderDelivery
        fields = (
            "id",
            "status",
            "recipient_count",
            "error_code",
            "created_at",
            "sent_at",
        )
        read_only_fields = fields
