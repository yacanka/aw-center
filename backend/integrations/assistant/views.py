"""Session-authenticated application guide and bounded conversation endpoints."""
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ParseError, UnsupportedMediaType
from rest_framework.parsers import BaseParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.api_errors import error_response
from integrations.ai import AIServiceError
from integrations.ai.config import configuration_status
from integrations.ai.transport import parse_json

from .access import authorized_guides
from .serializers import AssistantRequestSerializer, MAX_BODY_BYTES
from .service import answer_question, application_card
from .throttling import claim_request


def _read_input(request):
    if request.content_type != "application/json":
        raise UnsupportedMediaType(request.content_type)
    # Read the actual Django stream directly, with a bound, even when the caller
    # advertises a smaller/absent Content-Length that DRF uses to select a stream.
    django_request = request._request
    if hasattr(django_request, "_assistant_input"):
        return django_request._assistant_input
    body = django_request.read(MAX_BODY_BYTES + 1)
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("Body too large")
    data = parse_json(body.decode("utf-8"))
    django_request._assistant_input = data
    return data


class BoundedConversationParser(BaseParser):
    """CSRF checks may access DRF POST data before the handler; share its bound."""
    media_type = "application/json"

    def parse(self, stream, media_type=None, parser_context=None):
        try:
            return _read_input(parser_context["request"])
        except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError):
            raise ParseError("The conversation request is invalid.", code="VALIDATION_ERROR") from None


class AssistantCatalogView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "status": configuration_status(),
            "applications": [application_card(guide) for guide in authorized_guides(request.user)],
        })


class AssistantChatView(APIView):
    parser_classes = [BoundedConversationParser]
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            data = _read_input(request)
        except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError):
            return error_response("The conversation request is invalid.", "VALIDATION_ERROR")
        serializer = AssistantRequestSerializer(data=data)
        if not serializer.is_valid():
            return error_response("The conversation request is invalid.", "VALIDATION_ERROR", errors=serializer.errors)
        try:
            wait = claim_request(request.user)
            if wait is not None:
                response = error_response("Too many assistant requests.", "THROTTLED", response_status=429)
                response["Retry-After"] = str(wait)
                return response
            return Response(answer_question(request.user, **serializer.validated_data))
        except AIServiceError as error:
            return error_response(error.detail, error.code, response_status=error.response_status)
