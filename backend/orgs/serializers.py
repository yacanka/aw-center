from django.utils.text import slugify

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import  Project, Panel, Responsible, People
from .fields import RNameWSlugRelatedField

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = '__all__'

        extra_kwargs = {
            'slug': {'read_only': True}
        }
    
    def create(self, validated_data):
        name = validated_data.get("name", "")
        validated_data["slug"] = slugify(name)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            name = validated_data.get("name", "")
            validated_data["slug"] = slugify(name)
        
        return super().update(instance, validated_data)

class PanelSerializer(serializers.ModelSerializer):
    project = serializers.SlugRelatedField(slug_field="name", queryset=Project.objects.all())

    class Meta:
        model = Panel
        fields = '__all__'
        read_only_fields = ['slug']
        validators = [
            UniqueTogetherValidator(
                queryset=Panel.objects.all(),
                fields=["project", "ata"],
                message="This ATA chapter already exists."
            )
        ]
    
    def create(self, validated_data):
        name = validated_data.get("name", "")
        validated_data["slug"] = slugify(name)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            name = validated_data.get("name", "")
            validated_data["slug"] = slugify(name)
        
        return super().update(instance, validated_data)

class ResponsibleSerializer(serializers.ModelSerializer):
    project = serializers.SlugRelatedField(slug_field="name", queryset=Project.objects.all())
    panel = serializers.SlugRelatedField(slug_field="ata", queryset=Panel.objects.all())
    panel_name = serializers.CharField(source="panel.name", read_only=True)

    class Meta:
        model = Responsible
        fields = ['id', 'project', 'panel', 'name', 'email', 'title', 'panel_name', 'person_id']

class PeopleSerializer(serializers.ModelSerializer):
    class Meta:
        model = People
        fields = '__all__'

    def create(self, validated_data):
        person_id = validated_data.get('person_id')
        try:
            instance = People.objects.get(person_id=person_id)
            return instance
        except People.DoesNotExist:
            return super().create(validated_data)