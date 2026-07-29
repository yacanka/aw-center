from rest_framework.serializers import ModelSerializer
from rest_framework import serializers
import re

CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

def history_serializer_factory(model_class):
    class DynamicHistorySerializer(ModelSerializer):
        history_user = serializers.StringRelatedField()
        history_type = serializers.CharField(source="get_history_type_display")

        class Meta:
            model = model_class.history.model
            fields = ['history_id', 'history_date', 'history_type', 'history_user']

    return DynamicHistorySerializer

def serializer_factory(model_class):
    if hasattr(model_class, "history"):
        return versioned_serializer_factory(model_class)

    class DynamicSerializer(ModelSerializer):
        class Meta:
            model = model_class
            fields = '__all__'

    return DynamicSerializer


def versioned_serializer_factory(model_class):
    """Return a CompDoc serializer exposing its read-only current history version."""

    class DynamicVersionedSerializer(ModelSerializer):
        source_history_id = serializers.IntegerField(read_only=True)
        change_reason = serializers.CharField(
            write_only=True,
            required=False,
            allow_blank=True,
            max_length=100,
            trim_whitespace=True,
        )

        def validate(self, attributes):
            """Reject duplicate document names within the resolved project cover page."""

            number = str(
                attributes.get("cover_page_no", getattr(self.instance, "cover_page_no", ""))
            ).strip()
            name = str(attributes.get("name", getattr(self.instance, "name", ""))).strip()
            if not number:
                raise serializers.ValidationError({"cover_page_no": "This field may not be blank."})
            attributes["cover_page_no"] = number
            attributes["name"] = name
            if not name:
                raise serializers.ValidationError({"name": "This field may not be blank."})
            self._protect_workflow_history(attributes)
            attributes.pop("change_reason", None)
            self._validate_bounded_text(attributes)
            self._validate_workflow(attributes)
            self._validate_panel_ata(attributes)
            self._normalize_lists(attributes)
            queryset = model_class.objects.filter(cover_page_no=number, name=name)
            if self.instance is not None:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError(
                    {"name": "This compliance document already exists on the cover page."}
                )
            return attributes

        def _protect_workflow_history(self, attributes):
            """Ignore unchanged projections and reject direct workflow mutations."""

            if self.instance is None or "status_flow" not in attributes:
                return
            if attributes["status_flow"] != self.instance.status_flow:
                raise serializers.ValidationError(
                    {"status_flow": "Use the workflow transition action to change status."}
                )
            attributes.pop("status_flow")

        def _validate_panel_ata(self, attributes):
            panel = attributes.get("panel", getattr(self.instance, "panel", None))
            ata = attributes.get("ata", getattr(self.instance, "ata", None))
            if not panel or not ata:
                return
            if (
                not self.context.get("require_change_reason")
                and not {"panel", "ata"}.issubset(attributes)
            ):
                return
            if self.instance is not None:
                panel_changed = "panel" in attributes and panel != self.instance.panel
                ata_changed = "ata" in attributes and ata != self.instance.ata
                if not panel_changed and not ata_changed:
                    return
            panel_model = model_class._meta.apps.get_model(model_class._meta.app_label, "Panel")
            if not panel_model.objects.filter(name=panel, ata=ata).exists():
                raise serializers.ValidationError(
                    {"panel": "Panel and ATA must identify the same project panel."}
                )

        @staticmethod
        def _normalize_lists(attributes):
            for field in ("requirements", "signature_panel"):
                if field not in attributes:
                    continue
                values = attributes[field] or []
                if len(values) > 100:
                    raise serializers.ValidationError({field: "Use at most 100 values."})
                cleaned = []
                for value in values:
                    text = str(value).strip()
                    if text and text not in cleaned:
                        cleaned.append(text[:256])
                attributes[field] = cleaned

        @staticmethod
        def _validate_bounded_text(attributes):
            notes = attributes.get("notes")
            if notes is not None and len(notes) > 5000:
                raise serializers.ValidationError({"notes": "Use at most 5000 characters."})
            invalid = [
                field
                for field, value in attributes.items()
                if isinstance(value, str) and CONTROL_CHARACTERS.search(value)
            ]
            if invalid:
                raise serializers.ValidationError(
                    {field: "Control characters are not allowed." for field in invalid}
                )

        @staticmethod
        def _validate_workflow(attributes):
            if "status_flow" not in attributes:
                return
            flow = attributes["status_flow"]
            if not isinstance(flow, list) or len(flow) > 100:
                raise serializers.ValidationError(
                    {"status_flow": "Use a list with at most 100 workflow events."}
                )

        def to_representation(self, instance):
            """Expose cover-page compatibility fields from the canonical relation."""

            data = super().to_representation(instance)
            if instance.cover_page_id:
                data["cover_page_no"] = instance.cover_page.number
                data["cover_page_issue"] = instance.cover_page.issue
            return data

        class Meta:
            model = model_class
            fields = '__all__'
            read_only_fields = (
                "cover_page",
                "status",
                "ubm_target_date",
                "ubm_delivery_date",
                "owner",
                "owner_group",
                "next_action_due_date",
                "is_archived",
                "archived_at",
                "archived_by",
                "archive_reason",
            )

    return DynamicVersionedSerializer
