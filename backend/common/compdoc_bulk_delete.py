"""Explicit destructive confirmation for project CompDoc collection deletion."""

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response


class CompDocDeleteCountConflict(APIException):
    """Reject deletion when the reviewed row count is stale."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "COMPDOC_DELETE_COUNT_CONFLICT"
    default_detail = "The compliance document count changed. Review the current state first."


class CompDocBulkDeleteSerializer(serializers.Serializer):
    """Validate an explicit phrase and reviewed collection count."""

    confirmation = serializers.CharField(max_length=100, trim_whitespace=True)
    expected_count = serializers.IntegerField(min_value=0)


def delete_compdoc_collection(request, model):
    """Delete one project's collection after permission and state confirmation."""

    serializer = CompDocBulkDeleteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    _validate_confirmation(model, serializer.validated_data["confirmation"])
    expected_count = serializer.validated_data["expected_count"]
    with transaction.atomic():
        actual_count = model.objects.count()
        if actual_count != expected_count:
            raise CompDocDeleteCountConflict()
        model.objects.all().delete()
    return Response({"message": f"{actual_count} compliance documents deleted."})


def _validate_confirmation(model, supplied_confirmation):
    expected = bulk_delete_confirmation(model)
    if supplied_confirmation != expected:
        raise ValidationError({"confirmation": "The destructive confirmation phrase is invalid."})


def bulk_delete_confirmation(model):
    """Return the exact project-scoped destructive confirmation phrase."""

    return f"DELETE {model._meta.app_label.upper()} COMPLIANCE DOCUMENTS"
