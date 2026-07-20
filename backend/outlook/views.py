"""Authenticated Outlook message inspection and attachment downloads."""

import io
import mimetypes

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.crypto import get_random_string
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.file_security import MSG_POLICY, validate_request_upload
from jobs.contracts import JobExecutionFailure

from .message_helpers import (
    attachment_bytes,
    attachment_name,
    close_message,
    message_summary,
    open_message,
    safe_download_name,
)
from .throttles import OutlookParseThrottle

CACHE_PREFIX = "OUTLOOK_MESSAGE"
CACHE_SECONDS = 30 * 60


class MsgParseView(APIView):
    """Inspect one private MSG file and issue owner-bound attachment links."""

    parser_classes = (MultiPartParser, FormParser)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (OutlookParseThrottle,)

    def post(self, request, *args, **kwargs):
        """Return bounded plain-text metadata without embedding attachment bytes."""

        upload = validate_request_upload(request, "file", MSG_POLICY)
        message = None
        try:
            message = open_message(io.BytesIO(upload.read()))
            attachments, cached = collect_attachments(message.attachments)
            token = cache_attachments(request.user.pk, cached)
            add_download_links(attachments, token)
            return Response(
                {"mail": message_summary(message), "attachments": attachments},
                status=status.HTTP_200_OK,
            )
        except JobExecutionFailure as error:
            raise ValidationError(str(error), code=error.code) from error
        finally:
            close_message(message)


class MsgDownloadAttachmentView(APIView):
    """Download one cached attachment only for the user who parsed the message."""

    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        """Return a bounded owner-authorized attachment response."""

        token = str(request.query_params.get("token") or "")
        index = parse_index(request.query_params.get("index"))
        package = cache.get(cache_key(token)) if token else None
        if not package or package.get("owner_id") != request.user.pk:
            raise NotFound("The attachment link is unavailable.")
        attachments = package.get("attachments", ())
        if index >= len(attachments):
            raise NotFound("The attachment link is unavailable.")
        return attachment_response(attachments[index])


def collect_attachments(attachments):
    """Build bounded metadata and cache payloads for extracted attachments."""

    source = list(attachments)
    validate_attachment_count(source)
    metadata, cached, total = [], [], 0
    for attachment in source:
        content = attachment_bytes(attachment)
        total += len(content)
        if total > settings.AWCENTER_MAX_ATTACHMENT_UPLOAD_BYTES:
            raise JobExecutionFailure(
                "The message attachments exceed the safety limit.", "OUTLOOK_ATTACHMENT_LIMIT"
            )
        name = safe_download_name(attachment_name(attachment))
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        metadata.append({"name": name, "size": len(content), "mime": mime})
        cached.append({"name": name, "mime": mime, "bytes": content})
    return metadata, cached


def validate_attachment_count(attachments):
    """Reject messages that exceed the configured attachment count."""

    if len(attachments) > settings.OUTLOOK_MAX_ATTACHMENTS:
        raise JobExecutionFailure(
            "The message contains too many attachments.", "OUTLOOK_ATTACHMENT_LIMIT"
        )


def cache_attachments(owner_id, attachments):
    """Cache attachment bytes behind an unguessable owner-bound token."""

    token = get_random_string(48)
    cache.set(
        cache_key(token), {"owner_id": owner_id, "attachments": attachments}, CACHE_SECONDS
    )
    return token


def add_download_links(attachments, token):
    """Attach same-origin download links to response metadata."""

    for index, item in enumerate(attachments):
        item["download_url"] = f"/outlook/msg/download/?token={token}&index={index}"


def parse_index(value):
    """Validate a non-negative attachment index."""

    try:
        index = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError({"index": "Select a valid attachment index."}) from error
    if index < 0:
        raise ValidationError({"index": "Select a valid attachment index."})
    return index


def attachment_response(item):
    """Build a safe attachment download response."""

    response = HttpResponse(item["bytes"], content_type=item["mime"])
    response["Content-Length"] = str(len(item["bytes"]))
    response["Content-Disposition"] = f'attachment; filename="{item["name"]}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


def cache_key(token):
    """Return a namespace-isolated cache key."""

    return f"{CACHE_PREFIX}:{token}"
