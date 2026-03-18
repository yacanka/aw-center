from projects.aesa.models import CompDoc, Panel, Responsible

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
        """cover_page_issue = validated_data.get("cover_page_issue")
        if pd.notna(cover_page_issue):
            validated_data["cover_page_issue"] = int(float(cover_page_issue))
        
        tech_doc_no = validated_data.get("tech_doc_no")
        if pd.notna(tech_doc_no):
            tech_doc_numbers = [line.strip() for line in tech_doc_no.strip().splitlines() if line.strip()]
            validated_data["tech_doc_no"] = safe_get(tech_doc_numbers, 0)
            validated_data["tech_doc_no_2"] = safe_get(tech_doc_numbers, 1)
        
        tech_doc_issue = validated_data.get("tech_doc_issue")
        if pd.notna(tech_doc_issue):
            tech_doc_issues = [int(float(line.strip())) for line in tech_doc_issue.strip().splitlines() if line.strip()]
            validated_data["tech_doc_issue"] = safe_get(tech_doc_issues, 0)
            validated_data["tech_doc_issue_2"] = safe_get(tech_doc_issues, 1)
        
        delivered_tech_doc_issue = validated_data.get("delivered_tech_doc_issue")
        if pd.notna(delivered_tech_doc_issue):
            delivered_tech_doc_issues = [int(float(line.strip())) for line in delivered_tech_doc_issue.strip().splitlines() if line.strip()]
            validated_data["delivered_tech_doc_issue"] = safe_get(delivered_tech_doc_issues, 0)
            validated_data["delivered_tech_doc_issue_2"] = safe_get(delivered_tech_doc_issues, 1) """

        #instance = CompDoc.objects.create(**validated_data)
        instance, created = CompDoc.objects.update_or_create(
            cover_page_no=cover_page_no,
            defaults=validated_data
        )
        return instance

