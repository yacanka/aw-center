"""Project-model-bound API views for tracking and notifications."""

import re

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.api_errors import error_response
from common.compdoc_docproof import check_docproof
from common.compdoc_msg_draft import MsgDraftInputError, MsgDraftUnavailable, build_msg_draft
from common.compdoc_notification_events import detect_events
from common.compdoc_notifications import (
    build_notification_content,
    send_notification,
)
from common.compdoc_permissions import CompDocChangePermissions, StrictDjangoModelPermissions
from common.compdoc_tracking import (
    EVENT_KEYS,
    find_profile,
    tracking_payload,
    update_tracking_profile,
)
from common.compdoc_tracking_models import CompDocTrackingProfile


class TrackingProfileSerializer(serializers.Serializer):
    """Validate editable tracking preferences."""

    responsible_mode = serializers.ChoiceField(
        choices=CompDocTrackingProfile.ResponsibleMode.choices
    )
    responsible_person_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )
    notification_enabled = serializers.BooleanField()
    notification_events = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(EVENT_KEYS)),
        allow_empty=True,
    )


class NotificationRequestSerializer(serializers.Serializer):
    """Validate an explicit notification event request."""

    event_type = serializers.ChoiceField(choices=sorted(EVENT_KEYS))


def compdoc_tracking_view_factory(model):
    """Create a view/read and change/write tracking workspace."""
    class CompDocTrackingView(APIView):
        queryset = model.objects.none()
        permission_classes = [StrictDjangoModelPermissions]

        def get(self, request, pk):
            document = get_object_or_404(model, pk=pk)
            return Response(tracking_payload(model, document))

        def put(self, request, pk):
            document = get_object_or_404(model, pk=pk)
            serializer = TrackingProfileSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            profile = update_tracking_profile(
                model, document, serializer.validated_data, request.user
            )
            return Response(tracking_payload(model, document, profile))

    return CompDocTrackingView


def compdoc_docproof_view_factory(model):
    """Create a persisted, permission-protected DocProof check view."""

    class CompDocDocProofView(APIView):
        queryset = model.objects.none()
        permission_classes = [CompDocChangePermissions]

        def post(self, request, pk):
            document = get_object_or_404(model, pk=pk)
            profile = check_docproof(model, document, request.user)
            return Response(tracking_payload(model, document, profile))

    return CompDocDocProofView


def compdoc_notification_view_factory(model):
    """Create an explicit, idempotent notification delivery view."""

    class CompDocNotificationView(APIView):
        queryset = model.objects.none()
        permission_classes = [CompDocChangePermissions]

        def post(self, request, pk):
            document = get_object_or_404(model, pk=pk)
            serializer = NotificationRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            profile = find_profile(model, document.pk)
            if not profile:
                return _tracking_required_response("sending notifications")
            result = send_notification(
                model, document, profile, serializer.validated_data["event_type"]
            )
            return Response({**result, "tracking": tracking_payload(model, document, profile)})

    return CompDocNotificationView


def compdoc_notification_draft_view_factory(model):
    """Create an explicit Outlook MSG draft download view."""

    class CompDocNotificationDraftView(APIView):
        queryset = model.objects.none()
        permission_classes = [CompDocChangePermissions]

        def post(self, request, pk):
            document = get_object_or_404(model, pk=pk)
            serializer = NotificationRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            profile = find_profile(model, document.pk)
            if not profile:
                return _tracking_required_response("creating a message draft")
            event_type = serializer.validated_data["event_type"]
            return build_draft_response(model, document, profile, event_type)

    return CompDocNotificationDraftView


def build_draft_response(model, document, profile, event_type):
    """Return an editable MSG response for one currently applicable event."""

    applicability_error = _applicability_error(document, profile, event_type)
    if applicability_error:
        return applicability_error
    content = build_notification_content(model, document, profile, event_type)
    try:
        draft = build_msg_draft(
            content["subject"],
            content["html_body"],
            content["to_recipients"],
            content["cc_recipients"],
        )
    except MsgDraftInputError as error:
        return _draft_error_response(str(error), "COMPDOC_MSG_DRAFT_RECIPIENT_INVALID", 409)
    except MsgDraftUnavailable:
        return _draft_unavailable_response()
    return _msg_response(draft, _draft_filename(model, document, event_type))


def _applicability_error(document, profile, event_type):
    if event_type in detect_events(document, profile):
        return None
    return error_response(
        "This alert is not currently applicable.",
        code="COMPDOC_NOTIFICATION_NOT_APPLICABLE",
        response_status=status.HTTP_409_CONFLICT,
    )


def _tracking_required_response(action):
    return error_response(
        f"Save tracking preferences before {action}.",
        code="COMPDOC_TRACKING_REQUIRED",
        response_status=status.HTTP_409_CONFLICT,
    )


def _draft_error_response(detail, code, response_status):
    return error_response(detail, code=code, response_status=response_status)


def _draft_unavailable_response():
    return _draft_error_response(
        "An Outlook message draft could not be created.",
        "COMPDOC_MSG_DRAFT_UNAVAILABLE",
        503,
    )


def _msg_response(content, filename):
    response = HttpResponse(content, content_type="application/vnd.ms-outlook")
    response["Content-Length"] = str(len(content))
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _draft_filename(model, document, event_type):
    reference = document.tech_doc_no or document.cover_page_no or document.pk
    safe_reference = re.sub(r"[^A-Za-z0-9._-]+", "-", str(reference)).strip("-")[:80]
    return f"{model._meta.app_label}-{safe_reference or 'document'}-{event_type}.msg"
