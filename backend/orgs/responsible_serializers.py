"""Shared serializer construction for project responsible assignments."""

from rest_framework import serializers

from .models import People


def responsible_serializer_factory(model_class, panel_class):
    """Build a serializer backed by the canonical people directory."""

    class ResponsibleSerializer(serializers.ModelSerializer):
        panel = serializers.SlugRelatedField(
            slug_field="ata", queryset=panel_class.objects.all()
        )
        panel_name = serializers.CharField(source="panel.name", read_only=True)
        person_id = serializers.SlugRelatedField(
            source="person",
            slug_field="person_id",
            queryset=People.objects.all(),
        )
        name = serializers.CharField(source="person.name", read_only=True)
        email = serializers.EmailField(source="person.email", read_only=True)

        class Meta:
            model = model_class
            fields = ["id", "panel", "title", "panel_name", "person_id", "name", "email"]

    return ResponsibleSerializer
