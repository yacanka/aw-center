"""Explainable priority scoring for compliance documents."""

from collections import Counter
from dataclasses import asdict, dataclass

from .risk_signals import build_risk_signals, stage_age_days

LEVEL_KEYS = ("very_high", "high", "medium", "low")


@dataclass(frozen=True)
class RiskPolicy:
    """Versioned thresholds and boundaries for deterministic risk scoring."""

    version: int = 2
    very_high_score: int = 90
    high_score: int = 70
    medium_score: int = 30
    max_score: int = 100
    priority_limit: int = 25


DEFAULT_RISK_POLICY = RiskPolicy()


def create_risk_state():
    """Create bounded aggregation state for project risk analytics."""

    return {
        "counts": Counter({key: 0 for key in LEVEL_KEYS}),
        "score_total": 0,
        "at_risk_count": 0,
        "max_score": 0,
        "priorities": [],
    }


def accumulate_document_risk(state, document, entries, status, today, policy):
    """Assess one document and update bounded project risk state."""

    item = assess_document_risk(document, entries, status, today, policy)
    state["counts"][item["level"]] += 1
    state["score_total"] += item["score"]
    state["max_score"] = max(state["max_score"], item["score"])
    if item["score"]:
        state["at_risk_count"] += 1
        _retain_priority(state["priorities"], item, policy.priority_limit)


def assess_document_risk(document, entries, status, today, policy=DEFAULT_RISK_POLICY):
    """Return a value-safe score with every contributing reason exposed."""

    stage_age = stage_age_days(entries, today)
    signals = build_risk_signals(document, today)
    score = min(policy.max_score, sum(signal["points"] for signal in signals))
    return {
        "document_id": str(document["id"]),
        "name": str(document.get("name") or "Unnamed document"),
        "panel": str(document.get("panel") or "Unassigned"),
        "ata": str(document.get("ata") or ""),
        "status": status,
        "stage_age_days": stage_age,
        "score": score,
        "level": _risk_level(score, policy),
        "signals": sorted(signals, key=lambda signal: (-signal["points"], signal["code"])),
    }


def serialize_risk(state, total, policy=DEFAULT_RISK_POLICY):
    """Return the stable dashboard risk contract and active policy metadata."""

    return {
        "counts": dict(state["counts"]),
        "at_risk_count": state["at_risk_count"],
        "average_score": round(state["score_total"] / total, 1) if total else 0,
        "max_score": state["max_score"],
        "priorities": state["priorities"],
        "policy": asdict(policy),
    }


def _risk_level(score, policy):
    if score >= policy.very_high_score:
        return "very_high"
    if score >= policy.high_score:
        return "high"
    if score >= policy.medium_score:
        return "medium"
    return "low"


def _retain_priority(priorities, item, limit):
    priorities.append(item)
    priorities.sort(key=_priority_sort_key)
    del priorities[limit:]


def _priority_sort_key(item):
    return (-item["score"], -item["stage_age_days"], item["name"].casefold(), item["document_id"])
