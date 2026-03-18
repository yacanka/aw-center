from rest_framework import serializers
from .models import DDF

class DDFSerializer(serializers.ModelSerializer):
    class Meta:
        model = DDF
        fields = ['id', 'project', 'doc_name', 'doc_no', 'doc_issue', 'date', 'commentor', 'comments', 'comment_types', 'path']
        #read_only_fields = ['created_by', 'created_time']
    
    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["created_by"] = user
        return super().create(validated_data)