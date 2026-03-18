from rest_framework import serializers
from .models import JIRA_DCC

class JIRA_DCC_Serializer(serializers.ModelSerializer):

    class Meta:
        model = JIRA_DCC
        fields = ['id', 'issue', 'ecd_name', 'dcc_path', 'active']