from projects.gokbey.models import CompDoc, Panel, Responsible

from common.serializers import serializer_factory, history_serializer_factory
from orgs.responsible_serializers import responsible_serializer_factory

CompDocSerializerBase = serializer_factory(CompDoc)
HistorySerializerBase = history_serializer_factory(CompDoc)

PanelSerializerBase = serializer_factory(Panel)
ResponsibleSerializer = responsible_serializer_factory(Responsible, Panel)

class PanelSerializer(PanelSerializerBase):
    pass

class HistorySerializer(HistorySerializerBase):
    pass

class CompDocSerializer(CompDocSerializerBase):
    pass
