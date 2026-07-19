import math


def bounded_score(value):
    """Normalize model output into a finite zero-to-one score."""

    try:
        score = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, score)), 6) if math.isfinite(score) else 0.0


def bounded_index(value):
    """Return a non-negative evidence index or no index."""

    return value if isinstance(value, int) and value >= 0 else None


def score_status(score):
    """Map explainable retrieval scores to stable UI status bands."""

    if score >= 0.78:
        return "success"
    if score >= 0.58:
        return "warning"
    return "error"
