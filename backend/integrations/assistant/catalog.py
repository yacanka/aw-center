"""Validated, immutable guide data shared with route contract tests."""
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GuideEntry:
    id: str
    title: str
    path: str
    purpose: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    steps: tuple[str, ...]
    limitations: tuple[str, ...]
    keywords: tuple[str, ...]


GUIDE_DATA_PATH = Path(__file__).with_name("guide_data.json")


def load_guides(path: Path = GUIDE_DATA_PATH) -> tuple[GuideEntry, ...]:
    """Load canonical data, failing closed on invalid fields or duplicate IDs."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Guide data must be a list.")
    entries = []
    ids = set()
    paths = set()
    text_fields = ("id", "title", "path", "purpose")
    list_fields = ("inputs", "outputs", "steps", "limitations", "keywords")
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(text_fields + list_fields):
            raise ValueError("Invalid guide fields.")
        if any(not isinstance(row[key], str) or not row[key].strip() for key in text_fields):
            raise ValueError("Invalid guide text.")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", row["id"]):
            raise ValueError("Invalid guide ID.")
        if not re.fullmatch(r"/[A-Za-z0-9/_-]+", row["path"]) or "//" in row["path"]:
            raise ValueError("Invalid guide path.")
        for key in list_fields:
            if not isinstance(row[key], list) or any(
                not isinstance(value, str) or not value.strip() for value in row[key]
            ):
                raise ValueError("Invalid guide list.")
        if row["id"] in ids or row["path"] in paths:
            raise ValueError("Duplicate guide ID or path.")
        ids.add(row["id"])
        paths.add(row["path"])
        entries.append(GuideEntry(**{
            **row, **{key: tuple(row[key]) for key in list_fields},
        }))
    return tuple(entries)
