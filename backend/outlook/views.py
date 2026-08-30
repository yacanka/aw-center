"""Authenticated Outlook message inspection and attachment downloads."""

import io
import hashlib
import mimetypes
import secrets

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
from awcenter.api_errors import error_response
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
            capabilities = cache_attachments(request.user.pk, cached)
            add_download_capabilities(attachments, capabilities)
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

    def post(self, request, *args, **kwargs):
        """Return a bounded owner-authorized attachment response."""

        capability = str(request.data.get("capability") or "")
        package = consume_attachment_capability(capability, request.user.pk)
        if package is None:
            raise NotFound("The attachment link is unavailable.")
        attachment = package.get("attachment") or {}
        content = attachment.get("bytes")
        expected_digest = package.get("sha256")
        if not isinstance(content, bytes) or not isinstance(expected_digest, str):
            raise NotFound("The attachment link is unavailable.")
        actual_digest = hashlib.sha256(content).hexdigest()
        if not secrets.compare_digest(actual_digest, expected_digest):
            return error_response(
                "The attachment failed integrity verification.",
                "OUTLOOK_ATTACHMENT_INTEGRITY_FAILED",
                response_status=409,
            )
        return attachment_response(attachment)


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
    """Cache each attachment behind a single-use owner-bound capability."""

    capabilities = []
    for attachment in attachments:
        capability = get_random_string(48)
        cache.set(
            cache_key(capability),
            {
                "owner_id": owner_id,
                "attachment": attachment,
                "sha256": hashlib.sha256(attachment["bytes"]).hexdigest(),
            },
            CACHE_SECONDS,
        )
        capabilities.append(capability)
    return capabilities


def add_download_capabilities(attachments, capabilities):
    """Attach in-memory POST capabilities without putting secrets in URLs."""

    for item, capability in zip(attachments, capabilities, strict=True):
        item["download_capability"] = capability


def valid_capability(value):
    """Accept only the fixed-size alphabet used by Django's secure token generator."""

    return len(value) == 48 and value.isalnum()


def consume_attachment_capability(capability, owner_id):
    """Atomically fence one owner-bound capability before returning its payload."""

    if not valid_capability(capability):
        return None
    key = cache_key(capability)
    package = cache.get(key)
    if not package or package.get("owner_id") != owner_id:
        return None
    # ``add`` is the portable atomic cache primitive supported by both Redis
    # and the local test backend.  Keep the consumed marker for the full
    # capability lifetime so a crash between the fence and payload deletion
    # cannot make the token reusable.
    if not cache.add(consumed_cache_key(capability), True, CACHE_SECONDS):
        return None
    package = cache.get(key)
    if not package or package.get("owner_id") != owner_id:
        return None
    cache.delete(key)
    return package


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


def consumed_cache_key(token):
    """Return the atomic replay-fence key for an attachment capability."""

    return f"{cache_key(token)}:consumed"
