"""Bounded request contracts for credential-free JIRA subtask workflows."""

from rest_framework import serializers

from integrations.jira.contracts import validate_extra_fields

MAX_SUBTASKS_PER_BATCH = 100
PROTECTED_FIELDS = frozenset(
    {"project", "parent", "issuetype", "summary", "description", "assignee", "duedate"}
)


class SubtaskTargetSerializer(serializers.Serializer):
    issue = serializers.CharField(min_length=1, max_length=2048, trim_whitespace=True)


class SubtaskItemSerializer(serializers.Serializer):
    summary = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=30000,
        trim_whitespace=True,
    )
    assignee = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
        trim_whitespace=True,
    )
    due_date = serializers.DateField(required=False, allow_null=True, default=None)
    fields = serializers.JSONField(required=False, default=dict)

    def validate_fields(self, value):
        fields = validate_extra_fields(value)
        forbidden = sorted(set(fields) & PROTECTED_FIELDS)
        if forbidden:
            raise serializers.ValidationError(
                f"Protected JIRA fields cannot be overridden: {', '.join(forbidden)}"
            )
        labels = fields.get("labels") or []
        if not isinstance(labels, list) or any(
            not isinstance(label, str) or label.strip().lower().startswith("awcenter-st-")
            for label in labels
        ):
            raise serializers.ValidationError(
                "Labels must be a list of strings without reserved subtask markers."
            )
        return fields


class SubtaskBatchSerializer(SubtaskTargetSerializer):
    items = SubtaskItemSerializer(many=True)

    def validate_items(self, value):
        if not 1 <= len(value) <= MAX_SUBTASKS_PER_BATCH:
            raise serializers.ValidationError(
                f"Create between 1 and {MAX_SUBTASKS_PER_BATCH} subtasks per batch."
            )
        return value


class SubtaskWorkbookMappingSerializer(serializers.Serializer):
    column = serializers.CharField(min_length=1, max_length=200, trim_whitespace=True)
    field = serializers.CharField(min_length=1, max_length=64, trim_whitespace=True)


class SubtaskWorkbookSerializer(SubtaskTargetSerializer):
    mapping = SubtaskWorkbookMappingSerializer(many=True)

    def validate_mapping(self, value):
        columns = [item["column"] for item in value]
        fields = [item["field"] for item in value]
        if not 1 <= len(value) <= 30:
            raise serializers.ValidationError("Map between 1 and 30 workbook columns.")
        if len(set(columns)) != len(columns) or len(set(fields)) != len(fields):
            raise serializers.ValidationError("Workbook columns and JIRA fields must be unique.")
        if "summary" not in fields:
            raise serializers.ValidationError("Map one workbook column to Summary.")
        return value
