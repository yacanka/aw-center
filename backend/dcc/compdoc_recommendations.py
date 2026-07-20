"""Explainable, bounded CompDoc recommendations for an immutable DCC snapshot."""

import re
import unicodedata

from .compdoc_bridge import resolve_compdoc_model
from .compdoc_capture import current_status, scalar

MAX_RECOMMENDATION_CANDIDATES = 500
MAX_RECOMMENDATIONS = 8
MIN_RECOMMENDATION_SCORE = 30
WORD_PATTERN = re.compile(r"[a-z0-9]+")
ATA_PATTERN = re.compile(r"\b(\d{2})[- ]?(\d{2})\b")
IGNORED_WORDS = {
    "and", "change", "document", "documents", "for", "from", "the", "with",
    "bir", "icin", "ile", "ve",
}


def recommend_compdocs(snapshot, user, excluded_ids=()):
    """Return safe, relevance-ranked CompDoc suggestions for one DCC owner."""

    project, model = resolve_compdoc_model(snapshot.get("project_slug", ""))
    if not can_view_model(user, model):
        return recommendation_summary(project.slug, [], False, False)
    documents, candidates_truncated = recommendation_candidates(model)
    context = recommendation_context(snapshot)
    excluded = {str(value) for value in excluded_ids}
    ranked = [score_document(document, context) for document in documents]
    accepted = [item for item in ranked if item and item["id"] not in excluded]
    accepted.sort(key=recommendation_sort_key)
    return recommendation_summary(
        project.slug, accepted[:MAX_RECOMMENDATIONS], True,
        candidates_truncated,
    )


def can_view_model(user, model):
    """Return whether the user may read the concrete project CompDoc model."""

    permission = f"{model._meta.app_label}.view_{model._meta.model_name}"
    return user.has_perm(permission)


def recommendation_candidates(model):
    """Read only bounded common fields needed for deterministic scoring."""

    fields = [
        "id", "name", "panel", "ata", "cover_page_no", "tech_doc_no",
        "status_flow", "created_time",
    ]
    if any(field.name == "tech_doc_no_2" for field in model._meta.fields):
        fields.append("tech_doc_no_2")
    rows = list(
        model.objects.only(*fields).order_by("-created_time", "name")[
            : MAX_RECOMMENDATION_CANDIDATES + 1
        ]
    )
    return rows[:MAX_RECOMMENDATION_CANDIDATES], len(rows) > MAX_RECOMMENDATION_CANDIDATES


def recommendation_context(snapshot):
    """Normalize captured fields without returning their content to the browser."""

    placeholders = snapshot.get("placeholders") or {}
    values = [value for value in placeholders.values() if isinstance(value, str)]
    values.extend(value for value in snapshot.get("panel_titles", []) if isinstance(value, str))
    text = normalize(" ".join(values))
    return {"text": f" {text} ", "words": meaningful_words(text), "atas": extract_atas(text)}


def score_document(document, context):
    """Build one suggestion only when explainable evidence reaches the threshold."""

    score, reasons = reference_score(document, context)
    score, reasons = add_match(score, reasons, ata_match(document, context))
    score, reasons = add_match(score, reasons, panel_match(document, context))
    score, reasons = add_match(score, reasons, name_match(document, context))
    if score < MIN_RECOMMENDATION_SCORE:
        return None
    return serialize_recommendation(document, min(score, 100), reasons)


def reference_score(document, context):
    """Prefer explicit cover-page and technical-document references."""

    references = [
        document.cover_page_no,
        document.tech_doc_no,
        getattr(document, "tech_doc_no_2", ""),
    ]
    matches = [scalar(value) for value in references if phrase_present(value, context["text"])]
    if not matches:
        return 0, []
    return 90, [f"Captured JIRA fields mention reference {matches[0]}."[:180]]


def ata_match(document, context):
    """Return an explainable ATA match contribution."""

    ata = normalize_ata(document.ata)
    if not ata or ata not in context["atas"]:
        return 0, ""
    return 70, f"ATA {ata} appears in the captured JIRA context."


def panel_match(document, context):
    """Return an explainable panel-name contribution."""

    panel = scalar(document.panel)
    if len(normalize(panel)) < 3 or not phrase_present(panel, context["text"]):
        return 0, ""
    return 55, f"Panel {panel} appears in the captured JIRA context."[:180]


def name_match(document, context):
    """Score meaningful document-name token overlap."""

    words = meaningful_words(normalize(document.name))
    shared = sorted(words.intersection(context["words"]))
    if len(shared) < 2 and not any(len(word) >= 7 for word in shared):
        return 0, ""
    score = min(45, 20 + len(shared) * 10)
    return score, f"Document-name terms match: {', '.join(shared[:4])}."[:180]


def add_match(score, reasons, match):
    """Add one weighted explanation when a matcher produced evidence."""

    contribution, reason = match
    if reason:
        reasons.append(reason)
    return score + contribution, reasons


def serialize_recommendation(document, score, reasons):
    """Expose bounded fields already covered by the user's model permission."""

    return {
        "id": str(document.pk), "name": scalar(document.name)[:256],
        "panel": scalar(document.panel)[:128], "ata": scalar(document.ata)[:5],
        "status": current_status(document.status_flow)[:64],
        "score": score, "reasons": reasons[:4],
    }


def recommendation_summary(project_slug, recommendations, available, truncated):
    """Return the typed, content-bounded preview summary contract."""

    return {
        "compdoc_recommendations_available": available,
        "compdoc_recommendation_project": project_slug if available else "",
        "compdoc_recommendation_count": len(recommendations),
        "compdoc_recommendations": recommendations,
        "compdoc_recommendation_candidates_truncated": truncated,
    }


def phrase_present(value, normalized_context):
    """Match a normalized multi-token phrase with explicit boundaries."""

    phrase = normalize(value)
    return len(phrase) >= 3 and f" {phrase} " in normalized_context


def meaningful_words(value):
    """Return stable non-trivial tokens for conservative name matching."""

    return {
        word
        for word in WORD_PATTERN.findall(value)
        if len(word) >= 3 and word not in IGNORED_WORDS
    }


def extract_atas(value):
    """Extract canonical ATA identifiers from captured text."""

    return {f"{first}-{second}" for first, second in ATA_PATTERN.findall(value)}


def normalize_ata(value):
    """Return a canonical ATA value when present."""

    match = ATA_PATTERN.search(scalar(value))
    return f"{match.group(1)}-{match.group(2)}" if match else ""


def normalize(value):
    """Normalize text for accent-independent deterministic matching."""

    translated = scalar(value).casefold().translate(str.maketrans({"ı": "i"}))
    decomposed = unicodedata.normalize("NFKD", translated)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(WORD_PATTERN.findall(plain))


def recommendation_sort_key(item):
    """Prefer stronger evidence, then stable human-readable ordering."""

    return -item["score"], normalize(item["name"]), item["id"]
