"""Deterministic guide selection without live application records."""
import json
import re
from dataclasses import asdict

from .catalog import GuideEntry

MAX_CONTEXT_BYTES = 64 * 1024
GENERAL_HELP = (
    "AW Center application guide. Use only these authorized entries. "
    "Ask for clarification when functionality is undocumented. "
    "The assistant provides guidance only; it does not execute actions or read live records."
)


def _is_project(entry: GuideEntry) -> bool:
    return entry.id.startswith("compliance-project-")


def _explicitly_selected(entry: GuideEntry, current_path: str, message: str) -> bool:
    if current_path == entry.path:
        return True
    # Whole names/slugs avoid selecting AESA merely because a substring appears.
    return any(re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", message.casefold())
               for term in entry.keywords[:2])


def build_context(guides, *, current_path: str, message: str) -> str:
    """Pack general help, exact authorized page, then keyword matches within 64 KiB UTF-8.

    Callers must supply newly authorized guides for every request. No history,
    credentials, URL queries, profile data or live project records are read here.
    Entire entries are included or omitted, preserving valid bounded JSON.
    current_guide_id identifies only an included authorized page, otherwise null.
    """
    entries = [entry for entry in guides
               if not _is_project(entry) or _explicitly_selected(entry, current_path, message)]
    query = message.casefold()
    entries.sort(key=lambda entry: (
        0 if entry.path == current_path else 1,
        -sum(keyword.casefold() in query for keyword in entry.keywords),
        entry.id,
    ))
    selected = []
    def serialize():
        current_guide_id = next((row["id"] for row in selected if row["path"] == current_path), None)
        return json.dumps({"general_help": GENERAL_HELP, "current_guide_id": current_guide_id, "guides": selected},
                          ensure_ascii=False, separators=(",", ":"))
    for entry in entries:
        selected.append(asdict(entry))
        if len(serialize().encode("utf-8")) > MAX_CONTEXT_BYTES:
            selected.pop()
    return serialize()
