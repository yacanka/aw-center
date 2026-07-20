"""Optimistic concurrency helpers for project compliance documents."""

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.response import Response


class CompDocVersionConflict(APIException):
    """Reject a write based on a superseded Simple History version."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "COMPDOC_VERSION_CONFLICT"
    default_detail = "This compliance document changed after you opened it."


class CompDocVersionRequired(APIException):
    """Reject a write that does not identify the version reviewed by the caller."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "COMPDOC_VERSION_REQUIRED"
    default_detail = "A current source history version is required."


def latest_history_id(model, compdoc_id):
    """Return the current Simple History version identifier for one CompDoc."""

    return model.history.filter(id=compdoc_id).order_by(
        "-history_date", "-history_id"
    ).values_list("history_id", flat=True).first()


def with_current_history_id(queryset):
    """Annotate a CompDoc queryset with its current history identifier."""

    history = queryset.model.history.model.objects.filter(id=OuterRef("pk")).order_by(
        "-history_date", "-history_id"
    )
    return queryset.annotate(
        source_history_id=Subquery(history.values("history_id")[:1])
    )


def object_with_current_history(model, pk):
    """Return one CompDoc annotated with its current history identifier."""

    return get_object_or_404(with_current_history_id(model.objects.all()), pk=pk)


@transaction.atomic
def update_versioned_compdoc(request, model, serializer_class, pk, partial):
    """Lock, version-check, validate, and update one CompDoc atomically."""

    expected_version = parse_expected_version(request.data)
    instance = get_object_or_404(model.objects.select_for_update(), pk=pk)
    if latest_history_id(model, pk) != expected_version:
        raise CompDocVersionConflict()
    serializer = serializer_class(instance, data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)
    instance._history_user = request.user
    serializer.save()
    serializer.instance.source_history_id = latest_history_id(model, pk)
    return Response(serializer.data, status=status.HTTP_200_OK)


def parse_expected_version(payload):
    """Validate the mandatory positive source history identifier."""

    field = serializers.IntegerField(min_value=1)
    try:
        return field.run_validation(payload.get("source_history_id"))
    except serializers.ValidationError as error:
        raise CompDocVersionRequired() from error
