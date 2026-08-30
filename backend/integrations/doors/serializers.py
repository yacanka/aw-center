import math

from rest_framework import serializers

DEFAULT_ATTRIBUTES = ["Object Heading", "Object Text"]
MAX_SCRIPT_MAPPINGS = 50


class ModuleSerializer(serializers.Serializer):
    """Validate a DOORS module path."""

    module_path = serializers.CharField(max_length=1024, trim_whitespace=True)


class ObjectReadSerializer(ModuleSerializer):
    """Validate compliance DOORS object read parameters."""

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


class ModuleExportSerializer(ModuleSerializer):
    """Validate a bounded full-module read used by compliance imports."""

    limit = serializers.IntegerField(default=1000, min_value=1, max_value=10000)


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
        if any(not str(name).strip() or len(str(name)) > 256 for name in attributes):
            raise serializers.ValidationError(
                "Attribute names must contain between 1 and 256 characters."
            )
        if any(
            isinstance(value, float) and not math.isfinite(value)
            for value in attributes.values()
        ):
            raise serializers.ValidationError("Numeric attribute values must be finite.")
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


class RequirementLinkSerializer(serializers.Serializer):
    """Validate the fixed-purpose Requirement PoC Linker contract."""

    ref_module_name = serializers.CharField(max_length=1024, trim_whitespace=True)
    target_module_name = serializers.CharField(max_length=1024, trim_whitespace=True)
    link_module_name = serializers.CharField(max_length=1024, trim_whitespace=True)
    ref_attr_poc = serializers.CharField(max_length=256, trim_whitespace=True)
    ref_attr_req = serializers.CharField(max_length=256, trim_whitespace=True)
    target_attr_poc = serializers.CharField(max_length=256, trim_whitespace=True)
    start_index = serializers.IntegerField(min_value=0, max_value=1_000_000)
    text_length = serializers.IntegerField(min_value=-1, max_value=1_000_000)
    direction = serializers.ChoiceField(choices=("ref2tar", "tar2ref"))
    activeness = serializers.BooleanField()

    def validate(self, attributes):
        """Reject a second handle to the same module within one DXL execution."""

        if attributes["ref_module_name"].casefold() == attributes[
            "target_module_name"
        ].casefold():
            raise serializers.ValidationError(
                "Reference and target modules must be different."
            )
        return attributes


class ScriptMappingSerializer(serializers.Serializer):
    """Validate one Excel column to DOORS attribute mapping."""

    excel = serializers.CharField(max_length=256, trim_whitespace=True)
    doors = serializers.CharField(max_length=256, trim_whitespace=True)
    search = serializers.BooleanField(default=False)


class ScriptGenerationSerializer(serializers.Serializer):
    """Validate the bounded mapping JSON carried by a multipart request."""

    json = serializers.JSONField(write_only=True)

    def validate_json(self, mappings):
        """Require one search key and unambiguous source/target mappings."""

        if not isinstance(mappings, list):
            raise serializers.ValidationError("Column mappings must be a JSON array.")
        if not 1 <= len(mappings) <= MAX_SCRIPT_MAPPINGS:
            raise serializers.ValidationError(
                f"Provide between 1 and {MAX_SCRIPT_MAPPINGS} column mappings."
            )
        serializer = ScriptMappingSerializer(data=mappings, many=True)
        serializer.is_valid(raise_exception=True)
        values = list(serializer.validated_data)
        if sum(bool(item["search"]) for item in values) != 1:
            raise serializers.ValidationError("Exactly one search mapping is required.")
        if has_duplicates(item["excel"] for item in values):
            raise serializers.ValidationError("Excel column mappings must be unique.")
        if has_duplicates(item["doors"] for item in values):
            raise serializers.ValidationError("DOORS attribute mappings must be unique.")
        return values


def has_duplicates(values):
    """Return whether normalized mapping names contain duplicates."""

    normalized = [value.casefold() for value in values]
    return len(normalized) != len(set(normalized))
