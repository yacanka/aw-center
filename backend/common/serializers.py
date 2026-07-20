from rest_framework.serializers import ModelSerializer
from rest_framework import serializers

def history_serializer_factory(model_class):
    class DynamicHistorySerializer(ModelSerializer):
        history_user = serializers.StringRelatedField()
        history_type = serializers.CharField(source="get_history_type_display")

        class Meta:
            model = model_class.history.model
            fields = ['history_id', 'history_date', 'history_type', 'history_user']

    return DynamicHistorySerializer

def serializer_factory(model_class):
    if hasattr(model_class, "history"):
        return versioned_serializer_factory(model_class)

    class DynamicSerializer(ModelSerializer):
        class Meta:
            model = model_class
            fields = '__all__'

    return DynamicSerializer


def versioned_serializer_factory(model_class):
    """Return a CompDoc serializer exposing its read-only current history version."""

    class DynamicVersionedSerializer(ModelSerializer):
        source_history_id = serializers.IntegerField(read_only=True)

        class Meta:
            model = model_class
            fields = '__all__'

    return DynamicVersionedSerializer
