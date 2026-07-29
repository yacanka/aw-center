"""Atomic bounded bulk operations for project compliance documents."""

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from common.compdoc_lifecycle import set_archive_state, transition_document, update_work
from common.compdoc_lifecycle_views import (
    TransitionSerializer,
    WorkSerializer,
    validate_assignment,
)
from common.compdoc_versions import latest_history_id


class BulkConflict(APIException):
    """Report bounded optimistic conflicts without partially writing a batch."""

    status_code = 409
    default_code = "COMPDOC_BULK_CONFLICT"
    default_detail = "One or more documents changed. Reload the selection and try again."


class BulkDocumentSerializer(serializers.Serializer):
    """Validate one explicit document and version pair."""

    id = serializers.UUIDField()
    source_history_id = serializers.IntegerField(min_value=1)


class BulkRequestSerializer(serializers.Serializer):
    """Validate one bounded homogeneous bulk command."""

    documents = BulkDocumentSerializer(many=True, min_length=1, max_length=100)
    action = serializers.ChoiceField(choices=["work", "transition", "archive", "restore"])
    reason = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=255, trim_whitespace=True
    )
    values = serializers.JSONField(required=False, default=dict)

    def validate_documents(self, documents):
        identifiers = [item["id"] for item in documents]
        if len(set(identifiers)) != len(identifiers):
            raise serializers.ValidationError("Document identifiers must be unique.")
        return documents


def bulk_view_factory(model):
    """Create a project-bound atomic bulk endpoint."""

    class BulkView(APIView):
        queryset = model.objects.none()

        @transaction.atomic
        def post(self, request):
            serializer = BulkRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            _require_action_permission(request.user, model, data["action"])
            documents = _lock_documents(model, data["documents"])
            results = [
                _apply_action(model, document, item, data, request.user)
                for item, document in documents
            ]
            return Response({"updated": results})

    return BulkView


def _lock_documents(model, requested):
    identifiers = [item["id"] for item in requested]
    found = {
        item.pk: item
        for item in model.objects.select_for_update().filter(pk__in=identifiers)
    }
    conflicts = []
    result = []
    for item in requested:
        document = found.get(item["id"])
        current = latest_history_id(model, item["id"]) if document else None
        if not document or current != item["source_history_id"]:
            conflicts.append({"id": item["id"], "current_source_history_id": current})
        else:
            result.append((item, document))
    if conflicts:
        raise BulkConflict(
            {
                "detail": BulkConflict.default_detail,
                "code": BulkConflict.default_code,
                "errors": {"conflicts": conflicts[:20]},
            }
        )
    return result


def _apply_action(model, document, item, command, user):
    payload = {
        **command["values"],
        "source_history_id": item["source_history_id"],
        "reason": command["reason"],
    }
    if command["action"] == "transition":
        values = _validated(TransitionSerializer, payload)
        updated, _ = transition_document(model, document, values, user)
    elif command["action"] == "work":
        values = _validated(WorkSerializer, payload)
        validate_assignment(model, values)
        updated = update_work(model, document, values, user)
    else:
        updated = set_archive_state(
            model, document, command["action"] == "archive", payload, user
        )
    return {"id": updated.pk, "source_history_id": latest_history_id(model, updated.pk)}


def _validated(serializer_class, payload):
    serializer = serializer_class(data=payload)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _require_action_permission(user, model, action):
    prefix = f"{model._meta.app_label}."
    name = model._meta.model_name
    required = {
        "archive": [f"{prefix}delete_{name}"],
        "restore": [f"{prefix}change_{name}", f"{prefix}delete_{name}"],
        "transition": [f"{prefix}change_{name}"],
        "work": [f"{prefix}change_{name}"],
    }[action]
    if not user.has_perms(required):
        raise PermissionDenied()
