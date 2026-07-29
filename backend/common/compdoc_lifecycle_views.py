"""Project-bound lifecycle, ownership, review and activity APIs."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common.compdoc_lifecycle import set_archive_state, transition_document, update_work
from common.compdoc_activity import build_activity_items
from common.compdoc_lifecycle_models import CompDocReviewTask, CompDocWorkflowEvent
from common.compdoc_permissions import (
    CompDocArchivePermissions,
    CompDocChangePermissions,
    CompDocRestorePermissions,
    StrictDjangoModelPermissions,
)
from common.compdoc_versions import latest_history_id
from common.compdoc_workflow import WORKFLOW_STATUSES


class TransitionSerializer(serializers.Serializer):
    source_history_id = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=sorted(WORKFLOW_STATUSES))
    effective_date = serializers.DateField()
    next_action_due_date = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=255, trim_whitespace=True
    )


class WorkSerializer(serializers.Serializer):
    source_history_id = serializers.IntegerField(min_value=1)
    owner = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True),
        allow_null=True,
        required=False,
    )
    owner_group = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(), allow_null=True, required=False
    )
    next_action_due_date = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=255, trim_whitespace=True
    )

    def validate(self, attributes):
        if not {"owner", "owner_group", "next_action_due_date"} & attributes.keys():
            raise serializers.ValidationError("Provide at least one work assignment value.")
        return attributes


class ArchiveSerializer(serializers.Serializer):
    source_history_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=255, trim_whitespace=True
    )


def transition_view_factory(model):
    class TransitionView(APIView):
        queryset = model.objects.none()
        permission_classes = [CompDocChangePermissions]
        def post(self, request, pk):
            serializer = TransitionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            document = get_object_or_404(model, pk=pk)
            updated, event = transition_document(model, document, serializer.validated_data, request.user)
            return Response({"document_id": str(updated.pk), "source_history_id":
                             latest_history_id(model, updated.pk), "event_id": str(event.pk)})
    return TransitionView


def work_view_factory(model):
    class WorkView(APIView):
        queryset = model.objects.none()
        permission_classes = [StrictDjangoModelPermissions]
        def get(self, request, pk):
            document = get_object_or_404(model.objects.select_related("owner", "owner_group"), pk=pk)
            return Response(_work_payload(model, document))
        def put(self, request, pk):
            serializer = WorkSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            validate_assignment(model, serializer.validated_data)
            document = get_object_or_404(model, pk=pk)
            updated = update_work(model, document, serializer.validated_data, request.user)
            return Response(_work_payload(model, updated))
    return WorkView


def archive_view_factory(model, archived):
    class ArchiveView(APIView):
        queryset = model.objects.none()
        permission_classes = [
            CompDocArchivePermissions if archived else CompDocRestorePermissions
        ]
        def post(self, request, pk):
            serializer = ArchiveSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            document = get_object_or_404(model, pk=pk)
            updated = set_archive_state(
                model, document, archived, serializer.validated_data, request.user
            )
            return Response({"id": str(updated.pk), "is_archived": updated.is_archived,
                             "source_history_id": latest_history_id(model, updated.pk)})
    return ArchiveView


def activity_view_factory(model):
    class ActivityView(APIView):
        queryset = model.objects.none()
        permission_classes = [StrictDjangoModelPermissions]
        def get(self, request, pk):
            document = get_object_or_404(model, pk=pk)
            page = _bounded_int(request.query_params.get("page"), 1, 10, 1)
            page_size = _bounded_int(request.query_params.get("page_size"), 1, 50, 25)
            events = CompDocWorkflowEvent.objects.filter(
                project_slug=model._meta.app_label, document_id=pk
            )[:100]
            reviews = CompDocReviewTask.objects.filter(
                project_slug=model._meta.app_label, document_id=pk
            )[:100]
            items = build_activity_items(document, events, reviews)
            start = (page - 1) * page_size
            results = items[start:start + page_size]
            return Response({
                "count": len(items),
                "next": page + 1 if start + page_size < len(items) else None,
                "previous": page - 1 if page > 1 else None,
                "results": results,
            })
    return ActivityView


def _work_payload(model, document):
    return {"owner": document.owner_id, "owner_username": getattr(document.owner, "username", ""),
            "owner_group": document.owner_group_id,
            "owner_group_name": getattr(document.owner_group, "name", ""),
            "next_action_due_date": document.next_action_due_date,
            "source_history_id": latest_history_id(model, document.pk)}


def _bounded_int(value, minimum, maximum, default):
    try:
        return min(max(int(value), minimum), maximum)
    except (TypeError, ValueError):
        return default


def validate_assignment(model, values):
    """Ensure owners and teams cannot be assigned across project boundaries."""

    permission_name = f"{model._meta.app_label}.view_{model._meta.model_name}"
    owner = values.get("owner")
    if owner and not owner.has_perm(permission_name):
        raise serializers.ValidationError({"owner": "User cannot view this project."})
    group = values.get("owner_group")
    if group and not group.permissions.filter(
        content_type__app_label=model._meta.app_label,
        codename=f"view_{model._meta.model_name}",
    ).exists():
        raise serializers.ValidationError({"owner_group": "Group cannot view this project."})
