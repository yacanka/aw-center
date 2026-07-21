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

        def validate(self, attributes):
            """Reject duplicate document names within the resolved project cover page."""

            number = attributes.get("cover_page_no", getattr(self.instance, "cover_page_no", None))
            name = attributes.get("name", getattr(self.instance, "name", None))
            queryset = model_class.objects.filter(cover_page_no=number, name=name)
            if self.instance is not None:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError(
                    {"name": "This compliance document already exists on the cover page."}
                )
            return attributes

        def to_representation(self, instance):
            """Expose cover-page compatibility fields from the canonical relation."""

            data = super().to_representation(instance)
            if instance.cover_page_id:
                data["cover_page_no"] = instance.cover_page.number
                data["cover_page_issue"] = instance.cover_page.issue
            return data

        class Meta:
            model = model_class
            fields = '__all__'
            read_only_fields = (
                "cover_page",
                "status",
                "ubm_target_date",
                "ubm_delivery_date",
            )

    return DynamicVersionedSerializer
