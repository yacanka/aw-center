"""Pure text parsing helpers for DCC workflows."""

import os
import re
from collections.abc import Iterable
from typing import Any


def check_filename(path: str, filename: str) -> bool:
    """Return whether a normalized file name exists below the given path."""
    for existing_name in os.listdir(path):
        normalized_name = normalize_filename(existing_name)
        if filename in normalized_name:
            return True
    return False


def normalize_filename(filename: str) -> str:
    """Remove separators used inconsistently in DCC file names."""
    return filename.strip().replace("-", "").replace("–", "").replace(" ", "")


def find_keyword_list2d(data: list[list[Any]], keyword: Any) -> tuple[int, int] | None:
    """Return the first row and column coordinates that exactly match keyword."""
    for row_index, row in enumerate(data):
        for column_index, item in enumerate(row):
            if keyword == item:
                return row_index, column_index
    return None


def check_panel_text(text: str) -> bool:
    """Return whether panel text starts a numbered bullet like '1.' or '1:'."""
    return bool(re.search(r"\b\d+[.:]", text))


def extract_text_from_text(text: str, search_text1: str = "", search_text2: str = "") -> str:
    """Extract text between optional start and end markers using legacy behavior."""
    if search_text1 == "":
        return text[: text.find(search_text2)]
    if search_text2 == "":
        start_point = text.find(search_text1) + len(search_text1)
        return text[start_point: len(text)]
    start_point = text.find(search_text1) + len(search_text1)
    end_point = text.find(search_text2, start_point)
    return text[start_point:end_point]


def make_surname_upper(fullname: str) -> str:
    """Uppercase the final word in a full name while preserving other words."""
    words = fullname.split()
    if not words:
        return fullname
    words[-1] = words[-1].upper()
    return " ".join(words)


def parse_labels(text: str) -> list[str]:
    """Convert a semicolon separated label string into normalized JIRA labels."""
    if not text:
        return []
    labels = [label.strip() for label in text.split(";") if label.strip()]
    return [label.lower().replace(" ", "_") for label in labels]


def parse_multiselect(text: str) -> list[dict[str, str]]:
    """Convert semicolon separated text into unique JIRA multiselect values."""
    if not text:
        return []
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for part in text.split(";"):
        append_unique_multiselect_item(items, seen, part)
    return items


def append_unique_multiselect_item(
    items: list[dict[str, str]], seen: set[str], raw_value: str
) -> None:
    """Append a multiselect item unless its case-insensitive value was seen."""
    value = raw_value.strip()
    if not value or value.lower() in seen:
        return
    seen.add(value.lower())
    items.append({"value": value})


def multiselect_to_text(values: Any) -> str:
    """Convert JIRA multiselect values to the legacy comma separated string."""
    if not values:
        return ""
    iterable_values = values if is_iterable_collection(values) else [values]
    result = [value for value in (extract_multiselect_value(item) for item in iterable_values) if value]
    return ", ".join(result)


def is_iterable_collection(values: Any) -> bool:
    """Return whether values should be treated as a multiselect collection."""
    return isinstance(values, Iterable) and not isinstance(values, (str, bytes, dict))


def extract_multiselect_value(item: Any) -> str | None:
    """Extract one display value from dicts, JIRA option-like objects, or strings."""
    if item is None:
        return None
    if isinstance(item, dict):
        return clean_text_value(item.get("value"))
    object_value = getattr(item, "value", None)
    if object_value:
        return clean_text_value(object_value)
    if isinstance(item, str):
        return clean_text_value(item)
    return None


def clean_text_value(value: Any) -> str | None:
    """Return a stripped string value or None when the value is blank."""
    if value is None:
        return None
    cleaned_value = str(value).strip()
    return cleaned_value or None


def classify_dcc(classification_list: list[tuple[str, Any]]) -> tuple[str | None, Any | None]:
    """Return the dominant DCC classification using the legacy priority order."""
    priority_map = {"Major": 1, "Minor-Additional Work": 2, "Minor-No Effect": 3}
    dominant = choose_dominant_classification(classification_list, priority_map)
    if dominant:
        return dominant[0], dominant[1]
    return None, None


def choose_dominant_classification(
    classification_list: list[tuple[str, Any]], priority_map: dict[str, int]
) -> tuple[str, Any] | None:
    """Select the classification with the smallest configured priority value."""
    dominant = None
    for classification in classification_list:
        priority = priority_map.get(classification[0])
        if priority and (dominant is None or priority < priority_map[dominant[0]]):
            dominant = classification
    return dominant
