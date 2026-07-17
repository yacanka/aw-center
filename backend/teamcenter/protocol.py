from collections.abc import Iterable
from typing import Any

from .exceptions import PartialErrorDetail, TeamcenterServiceError


def make_envelope(body: dict[str, Any]) -> dict[str, Any]:
    """Wrap a request body in the Teamcenter SOA envelope."""
    return {"header": {"state": {}, "policy": {}}, "body": body}


def candidate_partial_errors(data: dict[str, Any]) -> Iterable[Any]:
    """Yield partial-error containers from known Teamcenter response shapes."""
    for key in ("partialErrors", "PartialErrors"):
        if data.get(key):
            yield data[key]
    for service_key in ("ServiceData", "serviceData"):
        service_data = data.get(service_key)
        if not isinstance(service_data, dict):
            continue
        for key in ("partialErrors", "PartialErrors"):
            if service_data.get(key):
                yield service_data[key]


def normalize_error_items(container: Any) -> list[dict[str, Any]]:
    """Normalize a Teamcenter partial-error container."""
    if isinstance(container, list):
        return [item for item in container if isinstance(item, dict)]
    if not isinstance(container, dict):
        return []
    errors = container.get("errors")
    if isinstance(errors, list):
        return [item for item in errors if isinstance(item, dict)]
    return [container]


def parse_partial_errors(data: dict[str, Any]) -> list[PartialErrorDetail]:
    """Parse all recognized partial errors from a Teamcenter response."""
    details = []
    for container in candidate_partial_errors(data):
        details.extend(parse_error_item(item) for item in normalize_error_items(container))
    return details


def parse_error_item(error: dict[str, Any]) -> PartialErrorDetail:
    """Convert one Teamcenter error object to a stable model."""
    raw_messages = error.get("messages") or error.get("errorValues") or error.get("message") or []
    if isinstance(raw_messages, str):
        messages = (raw_messages,)
    elif isinstance(raw_messages, list):
        messages = tuple(map(str, raw_messages))
    else:
        messages = (str(raw_messages),) if raw_messages else ()
    return PartialErrorDetail(error.get("code") or error.get("errorCode"), messages, error)


def raise_for_partial_errors(data: dict[str, Any]) -> None:
    """Raise when a Teamcenter response contains partial errors."""
    errors = parse_partial_errors(data)
    if errors:
        raise TeamcenterServiceError(errors)
