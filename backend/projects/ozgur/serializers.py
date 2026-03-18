from projects.ozgur.models import CompDoc, Panel, Responsible
from rest_framework import serializers

from common.serializers import serializer_factory, history_serializer_factory

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
    pass

