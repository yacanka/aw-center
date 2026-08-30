"""Organization API serializers with project scope supplied by the URL."""

from rest_framework import serializers

from .models import Panel, Person, ResponsibleAssignment


class PanelSerializer(serializers.ModelSerializer):
    project_slug = serializers.CharField(source="project.slug", read_only=True)

    class Meta:
        model = Panel
        fields = ("id", "project_slug", "name", "discipline", "ata")


class ResponsibleAssignmentSerializer(serializers.ModelSerializer):
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


class PersonSerializer(serializers.ModelSerializer):
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
