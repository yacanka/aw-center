from rest_framework import serializers
from .models import JIRA_DCC
from .services.jira_links import build_jira_issue_url


class JIRA_DCC_Serializer(serializers.ModelSerializer):
    jira_issue_url = serializers.SerializerMethodField()

    class Meta:
        model = JIRA_DCC
        fields = ['id', 'issue', 'jira_issue_url', 'ecd_name', 'dcc_path', 'active']

    def get_jira_issue_url(self, instance):
        """Return the backend-configured browser URL for the DCC issue."""

        return build_jira_issue_url(instance.issue)
