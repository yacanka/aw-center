"""Effectivity normalization and JIRA option matching helpers."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

EFFECTIVITY_GROUP_RE = re.compile(r"([^()]+?)\s*\(([A-Za-z0-9]+)\)")
SEPARATOR_RE = re.compile(r"[;,]\s*|\s{2,}")
OPTION_THRESHOLD = 0.72


def normalize_effectivity_text(text: str) -> str:
    """Convert ECR effectivity groups to semicolon separated backend values."""
    if not text:
        return ""
    values = []
    for match in EFFECTIVITY_GROUP_RE.finditer(text):
        values.extend(format_effectivity_group(match.group(2), match.group(1)))
    return "; ".join(values) if values else text.strip()


def match_effectivity_options(text: str, options: list[Any]) -> str:
    """Return semicolon separated closest JIRA option values for effectivity text."""
    normalized_text = normalize_effectivity_text(text)
    option_values = extract_option_values(options)
    if not option_values:
        return normalized_text
    normalized_values = split_effectivity_values(normalized_text)
    matched_values = [find_closest_option(value, option_values) for value in normalized_values]
    return "; ".join(deduplicate_values(matched_values))


def format_effectivity_group(prefix: str, raw_values: str) -> list[str]:
    """Format one ECR effectivity group such as '1-12, 80 (4AV)'."""
    values = [value for value in split_raw_values(raw_values) if value]
    has_multiple_values = len(values) > 1
    return [format_effectivity_value(prefix.strip(), value, has_multiple_values) for value in values]


def format_effectivity_value(prefix: str, value: str, has_multiple_values: bool) -> str:
    """Format one effectivity value with the aircraft prefix."""
    clean_value = value.strip()
    if has_multiple_values and "-" not in clean_value:
        return f"{prefix}-{clean_value}"
    return f"{prefix} {clean_value}"


def split_raw_values(raw_values: str) -> list[str]:
    """Split comma or semicolon separated raw effectivity values."""
    return [value.strip() for value in SEPARATOR_RE.split(raw_values.strip()) if value.strip()]


def split_effectivity_values(text: str) -> list[str]:
    """Split backend effectivity text by semicolon for multiselect matching."""
    return [value.strip() for value in text.split(";") if value.strip()]


def extract_option_values(options: list[Any]) -> list[str]:
    """Extract display values from JIRA allowedValues payloads."""
    values = [extract_option_value(option) for option in options]
    return [value for value in values if value]


def extract_option_value(option: Any) -> str:
    """Extract one option value from dicts, objects, or strings."""
    if isinstance(option, dict):
        return str(option.get("value") or option.get("name") or "").strip()
    value = getattr(option, "value", None) or getattr(option, "name", None) or option
    return str(value).strip() if value is not None else ""


def find_closest_option(value: str, options: list[str]) -> str:
    """Return the closest JIRA option when the similarity is confident."""
    best_option = max(options, key=lambda option: similarity_score(value, option))
    return best_option if similarity_score(value, best_option) >= OPTION_THRESHOLD else value


def similarity_score(left: str, right: str) -> float:
    """Calculate normalized text similarity for effectivity options."""
    return SequenceMatcher(None, comparable_text(left), comparable_text(right)).ratio()


def comparable_text(value: str) -> str:
    """Normalize effectivity text before fuzzy comparison."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def deduplicate_values(values: list[str]) -> list[str]:
    """Keep the first case-insensitive occurrence of each effectivity value."""
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result
