"""Compatibility adapter for document assessment through the shared AI client."""

from .ai import client as ai_client
from .ai.config import resolve_configuration
from .ai.contracts import AIRequestPolicy, AIServiceError, ChatMessage

# Document prompts are larger than chat messages; this accommodates the existing
# HTTP request budget even after requests' ASCII-escaped JSON encoding.
ASSESSMENT_MAX_REQUEST_BYTES = 16 * 1024 * 1024

_ERROR_CONTRACTS = {
    "AI_CONFIGURATION_ERROR": (
        "The assessment service is not configured safely.", "ASSESSMENT_CONFIGURATION_ERROR", 503,
    ),
    "AI_UNAVAILABLE": (
        "The assessment service is unavailable.", "ASSESSMENT_UNAVAILABLE", 503,
    ),
    "AI_UPSTREAM_REJECTED": (
        "The assessment service rejected the request.", "ASSESSMENT_UPSTREAM_REJECTED", 502,
    ),
    "AI_RESPONSE_INVALID": (
        "The assessment service returned an invalid response.", "ASSESSMENT_RESPONSE_INVALID", 502,
    ),
    "AI_INVALID_INPUT": (
        "The assessment request is invalid.", "ASSESSMENT_INVALID_INPUT", 400,
    ),
}


class AssessmentServiceError(RuntimeError):
    """Represent a sanitized assessment configuration or upstream failure."""

    def __init__(self, detail, code, response_status):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.response_status = response_status


def request_assessment(prompt):
    """Return complete chat content, preserving the assessment error contract.

    Prefer an active legacy provider family; otherwise use the central family.
    Prompts are sent unchanged as one user message without retries or history.
    Invalid input is rejected before network access with ASSESSMENT_INVALID_INPUT.
    """
    try:
        configuration = resolve_configuration(prefer_assessment=True)
        policy = AIRequestPolicy(
            purpose="assessment",
            max_request_bytes=ASSESSMENT_MAX_REQUEST_BYTES,
            max_response_bytes=configuration.max_response_bytes,
            connect_timeout=configuration.connect_timeout,
            read_timeout=configuration.read_timeout,
        )
        return ai_client.complete_text(
            [ChatMessage(role="user", content=prompt)],
            policy=policy,
            configuration=configuration,
        )
    except AIServiceError as error:
        detail, code, response_status = _ERROR_CONTRACTS[error.code]
        raise AssessmentServiceError(detail, code, response_status) from None
