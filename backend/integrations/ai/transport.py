"""One bounded synchronous HTTPS request; no sessions, retries or shared state."""

import json
import math
from typing import Any

import requests

from .contracts import AIConfiguration, AIRequestPolicy, AIServiceError


def invalid_response() -> AIServiceError:
    return AIServiceError(
        "The AI service returned an invalid response.", "AI_RESPONSE_INVALID", 502,
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON value")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite JSON value")
    return result


def parse_json(value: str) -> Any:
    """Parse strict JSON without duplicate keys or non-finite numeric literals."""
    return json.loads(value, object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant, parse_float=_finite_float)


def read_bounded_body(response, maximum_bytes: int) -> bytes:
    """Bound actual streamed bytes, including decompressed bodies and absent lengths."""
    body = bytearray()
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        if len(body) + len(chunk) > maximum_bytes:
            raise invalid_response()
        body.extend(chunk)
    return bytes(body)


def read_chat_content(response, maximum_bytes: int) -> str:
    """Require completed chat JSON and nonempty UTF-8 text; hide provider details."""
    try:
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Expected JSON")
        result = parse_json(read_bounded_body(response, maximum_bytes).decode("utf-8"))
        if not isinstance(result, dict) or any(key in result for key in ("error", "task_id", "task_ids")):
            raise ValueError("Expected completed response")
        choices = result.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Expected choices")
        answer = choices[0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Expected text")
        answer.encode("utf-8")
        return answer
    except (ValueError, UnicodeError, TypeError, KeyError, RecursionError, OverflowError):
        raise invalid_response() from None


def request_text(payload: dict[str, Any], *, policy: AIRequestPolicy, configuration: AIConfiguration) -> str:
    """Post the validated payload once, enforcing the stricter caller/provider limits."""
    timeout = (min(policy.connect_timeout, configuration.connect_timeout),
               min(policy.read_timeout, configuration.read_timeout))
    maximum_bytes = min(policy.max_response_bytes, configuration.max_response_bytes)
    try:
        with requests.post(
            configuration.url,
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json; charset=utf-8",
                     "Authorization": f"Bearer {configuration.token}"},
            timeout=timeout, stream=True, allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise AIServiceError(
                    "The AI service rejected the request.", "AI_UPSTREAM_REJECTED", 502,
                )
            return read_chat_content(response, maximum_bytes)
    except requests.RequestException:
        raise AIServiceError(
            "The AI service is unavailable.", "AI_UNAVAILABLE", 503,
        ) from None
