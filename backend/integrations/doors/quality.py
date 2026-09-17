"""Explainable, read-only ATA chapter/panel checks over a bounded module snapshot.

Attribute discovery tolerates separators, case, qualified names and small typos.
Panel values only ignore case and whitespace: fuzzy merging could hide a real
conflict. ATA section/subsection codes are grouped by their two-digit chapter.
"""

import re
import unicodedata
from difflib import SequenceMatcher

MAX_FINDINGS = 200
MAX_EVIDENCE = 20
ALIASES = {
    "ata": ("ata", "ata chapter", "ata chapters", "ata chapter number", "ata code"),
    "panel": ("panel", "panels", "panel name", "panel names", "panel id"),
}


def normalized_name(value):
    text = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def discover_attribute(columns, role):
    """Select one candidate only; ambiguity is a reportable coverage gap."""
    aliases = ALIASES[role]
    exact = [name for name in columns if normalized_name(name) in aliases]
    candidates = exact or [name for name in columns if heuristic_name(name, aliases)]
    return {
        "name": candidates[0] if len(candidates) == 1 else None,
        "method": ("exact" if exact else "heuristic") if len(candidates) == 1 else "unresolved",
        "candidates": candidates,
    }


def heuristic_name(name, aliases):
    normalized = normalized_name(name)
    words = normalized.split()
    for alias in aliases:
        if len(alias) >= 5 and SequenceMatcher(None, normalized, alias).ratio() >= 0.88:
            return True
        if len(words) <= 5 and re.search(r"\b" + re.escape(alias) + r"\b", normalized):
            return True
    return False


def chapters_from(value):
    """Accept chapter lists and conventional ATA section codes, never free-text digits."""
    chapters = set()
    for part in re.split(r"[,;|/\n]+", value):
        part = re.sub(r"^ata\s*(?:chapters?\s*)?[:#-]?\s*", "", part.strip(), flags=re.I)
        match = re.fullmatch(r"(\d{1,2})(?:\s*[-.]\s*\d{2}){0,2}", part, flags=re.ASCII)
        if not match:
            return set()
        chapters.add(match.group(1).zfill(2))
    return chapters


def panels_from(value):
    # Hyphens and slashes may be part of a panel identifier, so retain them.
    return {" ".join(part.split()).casefold() for part in re.split(r"[,;|\n]+", value) if part.strip()}


def evidence(row, ata, panel):
    return {
        "absolute_number": row["absolute_number"],
        "identifier": row.get("identifier", ""),
        "ata_value": ata[:500],
        "panel_value": panel[:500],
    }


def row_assignments(row, attributes):
    ata = str(row["attributes"].get(attributes["ata"]["name"]) or "").strip()
    panel = str(row["attributes"].get(attributes["panel"]["name"]) or "").strip()
    item = evidence(row, ata, panel)
    if not ata and not panel:
        return set(), set(), item, "unassigned"
    if not ata or not panel:
        return set(), set(), item, "missing_value"
    chapters, panels = chapters_from(ata), panels_from(panel)
    if not chapters or not panels:
        return set(), set(), item, "invalid_value"
    if len(chapters) > 1 and len(panels) > 1:
        return set(), set(), item, "ambiguous_assignment"
    return chapters, panels, item, ""


ROW_MESSAGES = {
    "missing_value": ("ATA chapter or panel is missing.", "Fill in the missing ATA chapter or panel attribute."),
    "invalid_value": ("The ATA chapter or panel could not be interpreted safely.", "Use a chapter such as 27 or 27-10-00 and a non-empty panel name."),
    "ambiguous_assignment": ("Multiple chapters and panels have no explicit pairing.", "Provide an unambiguous chapter-to-panel assignment before checking uniqueness."),
}


def make_finding(code, message, suggestion, items, *, chapter="", panels=None, evidence_count=None):
    return {
        "code": code, "message": message, "suggestion": suggestion,
        "chapter": chapter, "panels": panels or [],
        "evidence": items[:MAX_EVIDENCE],
        "evidence_count": len(items) if evidence_count is None else evidence_count,
    }


def record_assignment(assignments, chapters, panels, item):
    for chapter in sorted(chapters):
        group = assignments.setdefault(chapter, {})
        for panel in sorted(panels):
            entry = group.setdefault(panel, {"count": 0, "evidence": []})
            entry["count"] += 1
            if len(entry["evidence"]) < MAX_EVIDENCE:
                entry["evidence"].append(item)


def collect_assignments(rows, attributes, progress):
    """Keep all panel identities but only bounded evidence and row findings."""
    assignments, findings = {}, []
    counts = {"checked_objects": 0, "unassigned_objects": 0, "unresolved_objects": 0}
    for index, row in enumerate(rows):
        if index and index % 500 == 0:
            progress(55 + int(20 * index / len(rows)), "Step 3/5: Checking object attribute values.")
        chapters, panels, item, issue = row_assignments(row, attributes)
        if issue == "unassigned":
            counts["unassigned_objects"] += 1
            continue
        if issue:
            counts["unresolved_objects"] += 1
            if len(findings) < MAX_FINDINGS:
                findings.append(make_finding(issue, *ROW_MESSAGES[issue], [item]))
            continue
        counts["checked_objects"] += 1
        record_assignment(assignments, chapters, panels, item)
    return assignments, findings, counts


def conflict_findings(assignments):
    findings = []
    for chapter, panels in sorted(assignments.items()):
        if len(panels) <= 1:
            continue
        # Include an example from every panel before additional rows.
        items = [entry["evidence"][0] for entry in panels.values()]
        items.extend(item for entry in panels.values() for item in entry["evidence"][1:])
        findings.append(make_finding(
            "multiple_panels", "This ATA chapter belongs to more than one panel.",
            "Confirm the responsible panel and correct the conflicting object attributes in DOORS.",
            items, chapter=chapter, panels=sorted(panels),
            evidence_count=sum(entry["count"] for entry in panels.values()),
        ))
    return findings


def coverage_warnings(exported, attributes, counts):
    warnings = []
    for role, match in attributes.items():
        if not match["name"]:
            warnings.append(f"The {role} attribute is missing or ambiguous. Review the candidate attribute names.")
        elif match["method"] == "heuristic":
            warnings.append(f"The {role} attribute was selected heuristically. Confirm it in Details.")
    if exported["truncated"] or exported["attributes_truncated"]:
        warnings.append("The snapshot reached its object or attribute limit; the whole module was not checked.")
    if counts["unassigned_objects"]:
        warnings.append("Objects with both attributes empty were excluded; review their applicability.")
    if not exported["results"]:
        warnings.append("The module snapshot contains no objects; no assignment could be verified.")
    return warnings


def analyze_module(exported, progress):
    """Report conflicts and incomplete coverage without claiming engineering correctness."""
    progress(45, "Step 2/5: Discovering ATA chapter and panel attributes.")
    attributes = {role: discover_attribute(exported["columns"], role) for role in ALIASES}
    resolved = all(match["name"] for match in attributes.values())
    rows = exported["results"]
    progress(55, "Step 3/5: Normalizing chapter codes and panel names.")
    assignments, row_findings, counts = collect_assignments(rows if resolved else [], attributes, progress)
    progress(80, "Step 4/5: Checking that each ATA chapter belongs to one panel.")
    conflicts = conflict_findings(assignments)
    finding_count = len(conflicts) + counts["unresolved_objects"]
    complete = all((
        bool(rows), resolved, not exported["truncated"], not exported["attributes_truncated"],
        not counts["unassigned_objects"], not counts["unresolved_objects"],
    ))
    heuristic = any(match["method"] == "heuristic" for match in attributes.values())
    outcome = "review_required" if finding_count or heuristic else "passed" if complete else "incomplete"
    progress(95, "Step 5/5: Preparing findings and suggested corrections.")
    return {
        "type": "doors_module_quality", "schema_version": 1, "outcome": outcome,
        "complete": complete, "attributes": attributes,
        "warnings": coverage_warnings(exported, attributes, counts),
        "summary": {"scanned_objects": len(rows), "chapters": len(assignments), **counts,
                    "conflicting_chapters": len(conflicts),
                    "finding_count": finding_count, "omitted_findings": max(0, finding_count - MAX_FINDINGS)},
        "findings": (conflicts + row_findings)[:MAX_FINDINGS],
        "limits": {"objects": 10000, "attributes": 50, "findings": MAX_FINDINGS, "evidence_per_finding": MAX_EVIDENCE},
    }
