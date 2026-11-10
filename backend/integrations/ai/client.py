"""Stateless AI queries; domain prompts and result schemas remain with callers."""

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from requests.compat import json as request_json

from .config import resolve_configuration, validate_configuration, validated_timeout
from .contracts import AIConfiguration, AIRequestPolicy, AIServiceError, ChatMessage
from .transport import invalid_response, parse_json, request_text


def invalid_input() -> AIServiceError:
    return AIServiceError("The AI request is invalid.", "AI_INVALID_INPUT", 400)


def _validated_policy(policy: AIRequestPolicy) -> AIRequestPolicy:
    if not isinstance(policy, AIRequestPolicy):
        raise invalid_input()
    try:
        if not isinstance(policy.purpose, str) or not policy.purpose.strip():
            raise ValueError("Missing purpose")
        for limit in (policy.max_request_bytes, policy.max_response_bytes):
            if type(limit) is not int or limit <= 0:
                raise ValueError("Invalid byte limit")
        connect = validated_timeout(policy.connect_timeout, 60)
        read = validated_timeout(policy.read_timeout, 300)
    except (ValueError, TypeError, OverflowError):
        raise invalid_input() from None
    return replace(policy, connect_timeout=connect, read_timeout=read)


def _copied_messages(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)) or not messages:
        raise invalid_input()
    result = []
    for message in tuple(messages):
        if (not isinstance(message, ChatMessage) or message.role not in ("system", "user", "assistant")
                or not isinstance(message.content, str) or not message.content.strip()):
            raise invalid_input()
        try:
            message.content.encode("utf-8")
        except UnicodeError:
            raise invalid_input() from None
        result.append({"role": message.role, "content": message.content})
    return result


def complete_text(messages: Sequence[ChatMessage], *, policy: AIRequestPolicy,
                  configuration: AIConfiguration | None = None) -> str:
    """Return completed text from one request with caller-owned immutable limits.

    Invalid input/configuration fails before network access. Only model/messages/
    stream are sent. No history, credentials or mutable session survives this call.
    """
    policy = _validated_policy(policy)
    copied_messages = _copied_messages(messages)
    configuration = validate_configuration(
        resolve_configuration() if configuration is None else configuration,
    )
    payload = {"model": configuration.model, "messages": copied_messages, "stream": False}
    # Match requests' json= encoding exactly (including default ASCII escaping).
    encoded_payload = request_json.dumps(payload, allow_nan=False).encode("utf-8")
    if len(encoded_payload) > policy.max_request_bytes:
        raise invalid_input()
    return request_text(payload, policy=policy, configuration=configuration)


def complete_json(messages: Sequence[ChatMessage], *, policy: AIRequestPolicy,
                  configuration: AIConfiguration | None = None) -> dict[str, Any]:
    """Parse one bounded text completion as a strict JSON object without retries.

    Domain schema validation belongs to the caller. Arrays, null, duplicate keys
    and invalid JSON produce AI_RESPONSE_INVALID without another provider call.
    """
    content = complete_text(messages, policy=policy, configuration=configuration)
    try:
        result = parse_json(content)
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")
        return result
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise invalid_response() from None
