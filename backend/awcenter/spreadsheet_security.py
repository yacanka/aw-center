"""Neutralize untrusted values before writing spreadsheet cells."""

FORMULA_PREFIXES = frozenset("=+-@")


def spreadsheet_safe_value(value):
    """Return text that spreadsheet applications cannot interpret as a formula."""

    if not isinstance(value, str):
        return value
    candidate = value.lstrip()
    if candidate and candidate[0] in FORMULA_PREFIXES:
        return f"'{value}"
    return value


def spreadsheet_safe_rows(rows):
    """Copy dictionary rows while neutralizing every untrusted string value."""

    return [
        {spreadsheet_safe_value(key): spreadsheet_safe_value(value) for key, value in row.items()}
        for row in rows
    ]


def spreadsheet_safe_dataframe(dataframe):
    """Copy a pandas-like DataFrame and neutralize its headings and cell values."""

    safe = dataframe.copy()
    safe.columns = [spreadsheet_safe_value(value) for value in safe.columns]
    return safe.map(spreadsheet_safe_value)
