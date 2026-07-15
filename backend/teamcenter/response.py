import json
from typing import Any

from .exceptions import TeamcenterAuthenticationError, TeamcenterProtocolError
from .protocol import raise_for_partial_errors


def validate_response_status(response) -> None:
    """Reject HTTP failures and release the streamed connection."""
    if response.status_code < 400:
        return
    response.close()
    if response.status_code in {401, 403}:
        raise TeamcenterAuthenticationError("Teamcenter rejected the session.")
    raise TeamcenterProtocolError("Teamcenter returned an HTTP error.")


def declared_content_length(response) -> int:
    """Return a safe integer Content-Length value."""
    try:
        return int(response.headers.get("Content-Length", "0"))
    except ValueError:
        return 0


def read_bounded_content(response, limit: int) -> bytes:
    """Read streamed response content without exceeding a byte limit."""
    if declared_content_length(response) > limit:
        response.close()
        raise TeamcenterProtocolError("Teamcenter response exceeded the configured size limit.")
    chunks = []
    total = 0
    try:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            total += len(chunk)
            if total > limit:
                raise TeamcenterProtocolError("Teamcenter response exceeded the configured size limit.")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        response.close()


def parse_teamcenter_response(response, limit: int) -> dict[str, Any]:
    """Validate and parse a streamed Teamcenter JSON response."""
    validate_response_status(response)
    content = read_bounded_content(response, limit)
    text = content.decode(response.encoding or "utf-8", errors="replace")
    if text.lstrip().startswith("<"):
        raise TeamcenterProtocolError("Teamcenter returned HTML instead of JSON.")
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError) as error:
        raise TeamcenterProtocolError("Teamcenter returned invalid JSON.") from error
    if not isinstance(parsed, dict):
        raise TeamcenterProtocolError("Teamcenter returned a non-object JSON payload.")
    raise_for_partial_errors(parsed)
    return parsed
