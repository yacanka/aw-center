"""Project-scoped CompDoc review and assignee endpoints."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from common.compdoc_lifecycle import cancel_review, decide_review
from common.compdoc_lifecycle_models import CompDocReviewTask
from common.compdoc_permissions import (
    CompDocReviewActionPermissions,
    CompDocReviewAssigneePermissions,
    CompDocReviewChangePermissions,
)
from common.compdoc_versions import latest_history_id


class ReviewRequestSerializer(serializers.Serializer):
    """Validate a review or approval request."""

    kind = serializers.ChoiceField(choices=CompDocReviewTask.Kind.choices)
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True)
    )
    due_date = serializers.DateField(required=False, allow_null=True)
    request_note = serializers.CharField(min_length=3, max_length=500)
    source_history_id = serializers.IntegerField(min_value=1)


class ReviewDecisionSerializer(serializers.Serializer):
    """Validate a signed task decision."""

    status = serializers.ChoiceField(
        choices=[
            CompDocReviewTask.Status.APPROVED,
            CompDocReviewTask.Status.CHANGES_REQUESTED,
            CompDocReviewTask.Status.CANCELLED,
        ]
    )
    decision_note = serializers.CharField(min_length=3, max_length=500)


def review_view_factory(model):
    """Create a project-bound review collection endpoint."""

    class ReviewView(APIView):
        queryset = model.objects.none()
        permission_classes = [CompDocReviewChangePermissions]

        def get(self, request, pk):
            get_object_or_404(model, pk=pk)
            tasks = _tasks(model, pk)[:100]
            return Response({"results": [_task_payload(task) for task in tasks]})

        def post(self, request, pk):
            _require_project_permission(request.user, model, "change")
            document = get_object_or_404(model, pk=pk)
            serializer = ReviewRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data
            _require_current_version(model, document.pk, values["source_history_id"])
            _require_assignee_access(values["assignee"], model)
            task = CompDocReviewTask.objects.create(
                project_slug=model._meta.app_label,
                document_id=document.pk,
                assignee_username=values["assignee"].get_username(),
                requested_by=request.user,
                requested_by_username=request.user.get_username(),
                **values,
            )
            return Response(_task_payload(task), status=201)

    return ReviewView


def review_decision_view_factory(model):
    """Create a project-bound assigned-user decision endpoint."""

    class ReviewDecisionView(APIView):
        queryset = model.objects.none()
        permission_classes = [CompDocReviewActionPermissions]

        def post(self, request, pk, review_id):
            get_object_or_404(model, pk=pk)
            task = get_object_or_404(_tasks(model, pk), pk=review_id)
            serializer = ReviewDecisionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data
            if values["status"] == CompDocReviewTask.Status.CANCELLED:
                _require_project_permission(request.user, model, "change")
                task = cancel_review(task, values["decision_note"], request.user)
            else:
                task = decide_review(task, values["status"], values["decision_note"], request.user)
            return Response(_task_payload(task))

    return ReviewDecisionView


def assignee_view_factory(model):
    """Create a bounded project-visible user and group search endpoint."""

    class AssigneeView(APIView):
        queryset = model.objects.none()
        permission_classes = [CompDocReviewAssigneePermissions]

        def get(self, request):
            search = request.query_params.get("search", "").strip()[:100]
            users = _visible_users(model, search)[:25]
            groups = _visible_groups(model, search)[:25]
            return Response(
                {
                    "users": [{"id": user.pk, "username": user.get_username()} for user in users],
                    "groups": [{"id": group.pk, "name": group.name} for group in groups],
                }
            )

    return AssigneeView


def _tasks(model, document_id):
    return CompDocReviewTask.objects.select_related("assignee").filter(
        project_slug=model._meta.app_label, document_id=document_id
    )


def _require_project_permission(user, model, action):
    if user.has_perm("common.manage_compdoc_workflow"):
        return
    if not user.has_perm(f"{model._meta.app_label}.{action}_{model._meta.model_name}"):
        raise PermissionDenied()


def _require_current_version(model, document_id, expected):
    from common.compdoc_versions import CompDocVersionConflict

    if latest_history_id(model, document_id) != expected:
        raise CompDocVersionConflict()


def _require_assignee_access(user, model):
    if not user.has_perm(f"{model._meta.app_label}.view_{model._meta.model_name}"):
        raise serializers.ValidationError({"assignee": "User cannot view this project."})


def _visible_users(model, search):
    permission = _view_permission(model)
    query = Q(user_permissions=permission) | Q(groups__permissions=permission)
    queryset = get_user_model().objects.filter(is_active=True)
    if search:
        queryset = queryset.filter(username__icontains=search)
    return queryset.filter(Q(is_superuser=True) | query).distinct().order_by("username")


def _visible_groups(model, search):
    queryset = Group.objects.filter(permissions=_view_permission(model))
    if search:
        queryset = queryset.filter(name__icontains=search)
    return queryset.distinct().order_by("name")


def _view_permission(model):
    return Permission.objects.get(
        content_type__app_label=model._meta.app_label,
        codename=f"view_{model._meta.model_name}",
    )


def _task_payload(task):
    return {
        "id": task.pk,
        "kind": task.kind,
        "status": task.status,
        "assignee": task.assignee_id,
        "assignee_username": task.assignee_username,
        "due_date": task.due_date,
        "request_note": task.request_note,
        "decision_note": task.decision_note,
        "requested_by": task.requested_by_username,
        "decided_by": task.decided_by_username,
        "created_at": task.created_at,
        "decided_at": task.decided_at,
        "source_history_id": task.source_history_id,
    }
