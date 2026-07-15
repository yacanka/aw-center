from rest_framework import serializers


class ModelReferenceSerializer(serializers.Serializer):
    """Validate a Teamcenter model reference."""

    uid = serializers.CharField(max_length=128, trim_whitespace=True)
    type = serializers.CharField(max_length=128, default="WorkspaceObject")


class ExecuteSavedQuerySerializer(serializers.Serializer):
    """Validate a saved-query execution request."""

    query_uid = serializers.CharField(max_length=128, trim_whitespace=True)
    entries = serializers.ListField(
        child=serializers.CharField(max_length=256), min_length=1, max_length=25
    )
    values = serializers.ListField(
        child=serializers.CharField(max_length=1000, allow_blank=True), min_length=1, max_length=25
    )
    maximum = serializers.IntegerField(default=100, min_value=1, max_value=1000)

    def validate(self, attributes):
        """Require one value for every query entry."""
        if len(attributes["entries"]) != len(attributes["values"]):
            raise serializers.ValidationError("entries and values must have equal lengths.")
        return attributes


class LoadObjectsSerializer(serializers.Serializer):
    """Validate a bounded object load request."""

    uids = serializers.ListField(
        child=serializers.CharField(max_length=128, trim_whitespace=True),
        min_length=1,
        max_length=250,
    )


class GetPropertiesSerializer(serializers.Serializer):
    """Validate a Teamcenter property read request."""

    objects = ModelReferenceSerializer(many=True)
    properties = serializers.ListField(
        child=serializers.CharField(max_length=128, trim_whitespace=True),
        min_length=1,
        max_length=100,
    )

    def validate_objects(self, objects):
        """Limit the number of objects in one property read."""
        if not 1 <= len(objects) <= 250:
            raise serializers.ValidationError("Between 1 and 250 objects are required.")
        return objects


class PropertyUpdateSerializer(serializers.Serializer):
    """Validate one Teamcenter object property update."""

    object = ModelReferenceSerializer()
    properties = serializers.DictField(
        child=serializers.ListField(
            child=serializers.CharField(max_length=4000, allow_blank=True),
            min_length=1,
            max_length=100,
        ),
        allow_empty=False,
    )

    def validate_properties(self, properties):
        """Limit property names and update batch width."""
        if len(properties) > 50:
            raise serializers.ValidationError("At most 50 properties are supported per object.")
        if any(len(name) > 128 for name in properties):
            raise serializers.ValidationError("Property names cannot exceed 128 characters.")
        return properties


class SetPropertiesSerializer(serializers.Serializer):
    """Validate a bounded Teamcenter property update batch."""

    updates = PropertyUpdateSerializer(many=True, allow_empty=False)

    def validate_updates(self, updates):
        """Limit mutation batch size."""
        if len(updates) > 50:
            raise serializers.ValidationError("At most 50 objects can be updated at once.")
        return updates
