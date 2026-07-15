from rest_framework import serializers

DEFAULT_ATTRIBUTES = ["Object Heading", "Object Text"]


class ModuleSerializer(serializers.Serializer):
    """Validate a DOORS module path."""

    module_path = serializers.CharField(max_length=1024, trim_whitespace=True)


class ObjectReadSerializer(ModuleSerializer):
    """Validate common DOORS object read parameters."""

    attributes = serializers.ListField(
        child=serializers.CharField(max_length=256, trim_whitespace=True),
        default=DEFAULT_ATTRIBUTES,
        min_length=1,
        max_length=50,
    )


class ObjectListSerializer(ObjectReadSerializer):
    """Validate a bounded DOORS object list request."""

    loop = serializers.ChoiceField(
        choices=("module", "entire", "all", "document"), default="entire"
    )
    limit = serializers.IntegerField(default=250, min_value=1, max_value=1000)


class ObjectDetailSerializer(ObjectReadSerializer):
    """Validate a DOORS object detail request."""

    absolute_number = serializers.IntegerField(min_value=1)


class ScalarAttributesSerializer(ModuleSerializer):
    """Validate scalar DOORS attribute values."""

    attributes = serializers.DictField(
        child=serializers.JSONField(), allow_empty=False
    )

    def validate_attributes(self, attributes):
        """Reject nested values unsupported by the DXL scalar adapter."""
        if len(attributes) > 50:
            raise serializers.ValidationError("At most 50 attributes are supported.")
        if any(isinstance(value, (dict, list)) for value in attributes.values()):
            raise serializers.ValidationError("Only scalar attribute values are supported.")
        if any(len(str(name)) > 256 for name in attributes):
            raise serializers.ValidationError("Attribute names cannot exceed 256 characters.")
        return attributes


class ObjectUpdateSerializer(ScalarAttributesSerializer):
    """Validate a DOORS object update request."""

    absolute_number = serializers.IntegerField(min_value=1)


class ObjectCreateSerializer(ScalarAttributesSerializer):
    """Validate a DOORS object creation request."""

    position = serializers.ChoiceField(
        choices=("first", "after", "before", "below", "below_last"), default="after"
    )
    relative_absolute_number = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attributes):
        """Require a relative object for relative positions."""
        if attributes["position"] != "first" and "relative_absolute_number" not in attributes:
            raise serializers.ValidationError("relative_absolute_number is required.")
        return attributes
