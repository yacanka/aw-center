from rest_framework import serializers

class RNameWSlugRelatedField(serializers.RelatedField):
    default_error_messages = {
        "does_not_exist": "Invalid slug: '{value}'.",
        "invalid": "Invalid value."
    }

    def to_representation(self, value):
        if value is None:
            return None
            
        return getattr(value, 'name', str(value))

    def to_internal_value(self, data):
        if data is None:
            if self.allow_null:
                return None
            self.fail("invalid")
        if not isinstance(data, str):
            self.fail("invalid")
        qs = self.get_queryset()
        try:
            return qs.get(slug=data)
        except qs.model.DoesNotExist:
            self.fail("does_not_exist", value=data)
        