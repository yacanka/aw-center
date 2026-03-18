from projects.blok4050.models import CompDoc, Panel, Responsible

from rest_framework import serializers

from common.serializers import serializer_factory, history_serializer_factory

from utils.arrays import safe_get
import pandas as pd

CompDocSerializerBase = serializer_factory(CompDoc)
HistorySerializerBase = history_serializer_factory(CompDoc)

PanelSerializerBase = serializer_factory(Panel)
ResponsibleSerializerBase = serializer_factory(Responsible)

class ResponsibleSerializer(ResponsibleSerializerBase):
    panel = serializers.SlugRelatedField(slug_field="ata", queryset=Panel.objects.all())
    panel_name = serializers.CharField(source="panel.name", read_only=True)

class PanelSerializer(PanelSerializerBase):
    pass

class HistorySerializer(HistorySerializerBase):
    pass

class CompDocSerializer(CompDocSerializerBase):
    def create(self, validated_data):
        
        cover_page_no = validated_data.get("cover_page_no")
     
        #instance = CompDoc.objects.create(**validated_data)
        instance, created = CompDoc.objects.update_or_create(
            cover_page_no=cover_page_no,
            defaults=validated_data
        )
        return instance

