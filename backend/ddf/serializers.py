from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from .models import DDF

class DDFSerializer(serializers.ModelSerializer):
    @transaction.atomic
    def update(self, instance, validated_data):
        # Merge PATCH values into current state, not the earlier view snapshot.
        locked = get_object_or_404(DDF.objects.select_for_update(), pk=instance.pk)
        return super().update(locked, validated_data)

    class Meta:
        model = DDF
        fields = ['id', 'project', 'doc_name', 'doc_no', 'doc_issue', 'date', 'commentor', 'comments', 'comment_types', 'path']
        #read_only_fields = ['created_by', 'created_time']

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["created_by"] = user
        return super().create(validated_data)
