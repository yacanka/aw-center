from typing import Any


def dxl_quote(value: str) -> str:
    """Return a safely escaped DXL string literal."""
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def dxl_value(value: Any) -> str:
    """Convert a supported Python scalar into a DXL expression."""
    if value is None:
        return "(string null)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return dxl_quote(str(value))


def decode_field(value: str):
    """Decode the line-oriented escaping emitted by generated DXL."""
    if value == r"\N":
        return None
    output = []
    index = 0
    while index < len(value):
        consumed, decoded = decode_character(value, index)
        output.append(decoded)
        index += consumed
    return "".join(output)


def decode_character(value: str, index: int) -> tuple[int, str]:
    """Decode one escaped or plain character."""
    if value[index] != "\\" or index + 1 >= len(value):
        return 1, value[index]
    escaped = value[index + 1]
    replacements = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\"}
    return 2, replacements.get(escaped, escaped)
