"""Organization API serializers with project scope supplied by the URL."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from .models import Panel, Person, ResponsibleAssignment
from .ata import normalize_ata_chapter


class OrganizationModelSerializer(serializers.ModelSerializer):
    """Apply partial edits to a fresh row while holding the database write lock."""

    @transaction.atomic
    def update(self, instance, validated_data):
        # DRF reads the instance before save; even an atomic save can otherwise
        # restore unrelated values from that stale snapshot during a PATCH.
        locked = get_object_or_404(
            self.Meta.model.objects.select_for_update(), pk=instance.pk,
        )
        return super().update(locked, validated_data)


class PanelSerializer(OrganizationModelSerializer):
    ata = serializers.CharField(max_length=128)

    def validate_ata(self, value):
        try:
            return normalize_ata_chapter(value)
        except ValueError as error:
            raise serializers.ValidationError("Use an ATA chapter such as 27-00 or digit-free text.") from error

    project_slug = serializers.CharField(source="project.slug", read_only=True)

    class Meta:
        model = Panel
        fields = ("id", "project_slug", "name", "discipline", "ata")


class ResponsibleAssignmentSerializer(OrganizationModelSerializer):
    panel = serializers.PrimaryKeyRelatedField(queryset=Panel.objects.none())
    panel_name = serializers.CharField(source="panel.name", read_only=True)
    panel_ata = serializers.CharField(source="panel.ata", read_only=True)
    person_id = serializers.SlugRelatedField(
        source="person",
        slug_field="person_id",
        queryset=Person.objects.all(),
    )
    name = serializers.CharField(source="person.name", read_only=True)
    email = serializers.EmailField(source="person.email", read_only=True)

    class Meta:
        model = ResponsibleAssignment
        fields = (
            "id",
            "panel",
            "panel_name",
            "panel_ata",
            "person_id",
            "name",
            "email",
            "responsibility_role",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project = self.context.get("project")
        if project is not None:
            self.fields["panel"].queryset = Panel.objects.filter(project=project)

    def validate_panel(self, panel):
        project = self.context.get("project")
        if project is None or panel.project_id != project.pk:
            raise serializers.ValidationError("Panel must belong to the URL project.")
        return panel


class PersonSerializer(OrganizationModelSerializer):
    class Meta:
        model = Person
        fields = ("id", "person_id", "name", "email")

    def create(self, validated_data):
        person, _ = Person.objects.get_or_create(
            person_id=validated_data["person_id"],
            defaults={
                "name": validated_data["name"],
                "email": validated_data["email"],
            },
        )
        return person
