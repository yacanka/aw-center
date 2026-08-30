"""Validation shared by server-owned outbound HTTP integrations."""

from urllib.parse import unquote, urlsplit, urlunsplit


def normalize_outbound_base_url(value, *, require_https=False):
    """Return a canonical base URL without credentials or request-specific parts."""

    raw = str(value or "").strip()
    if any(ord(character) < 32 or character == "\\" for character in raw):
        raise ValueError("The integration URL contains unsupported characters.")
    try:
        parsed = urlsplit(raw)
        parsed.port
    except ValueError as error:
        raise ValueError("The integration URL is invalid.") from error
    allowed_schemes = {"https"} if require_https else {"http", "https"}
    if parsed.scheme.casefold() not in allowed_schemes or not parsed.hostname:
        raise ValueError("The integration URL must use an allowed HTTP(S) origin.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("The integration URL cannot contain credentials, a query, or a fragment.")
    decoded_segments = unquote(parsed.path).split("/")
    if any(segment in {".", ".."} for segment in decoded_segments):
        raise ValueError("The integration URL path cannot contain traversal segments.")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc, path, "", ""))
