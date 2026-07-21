"""Explainable priority scoring for compliance documents."""

from collections import Counter
from dataclasses import asdict, dataclass

from common.compdoc_risk_signals import build_risk_signals, stage_age_days

LEVEL_KEYS = ("high", "medium", "low", "none")


@dataclass(frozen=True)
class RiskPolicy:
    """Versioned thresholds and boundaries for deterministic risk scoring."""

    version: int = 1
    high_score: int = 60
    medium_score: int = 30
    long_wait_days: int = 30
    authority_aging_days: int = 14
    max_score: int = 100
    priority_limit: int = 25


DEFAULT_RISK_POLICY = RiskPolicy()


def get_dashboard_value_fields(model):
    """Return the minimal model fields required by dashboard and risk analytics."""

    field_names = {field.name for field in model._meta.fields}
    technical_fields = sorted(name for name in field_names if name.startswith("tech_doc_no"))
    return ["id", "name", "panel", "ata", "status_flow", *technical_fields]


def create_risk_state():
    """Create bounded aggregation state for project risk analytics."""

    return {
        "counts": Counter({key: 0 for key in LEVEL_KEYS}),
        "score_total": 0,
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
        _retain_priority(state["priorities"], item, policy.priority_limit)


def assess_document_risk(document, entries, status, today, policy=DEFAULT_RISK_POLICY):
    """Return a value-safe score with every contributing reason exposed."""

    stage_age = stage_age_days(entries, today)
    signals = build_risk_signals(document, entries, status, stage_age, today, policy)
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
        "at_risk_count": total - state["counts"]["none"],
        "average_score": round(state["score_total"] / total, 1) if total else 0,
        "max_score": state["max_score"],
        "priorities": state["priorities"],
        "policy": asdict(policy),
    }


def _risk_level(score, policy):
    if score >= policy.high_score:
        return "high"
    if score >= policy.medium_score:
        return "medium"
    return "low" if score else "none"


def _retain_priority(priorities, item, limit):
    priorities.append(item)
    priorities.sort(key=_priority_sort_key)
    del priorities[limit:]


def _priority_sort_key(item):
    return (-item["score"], -item["stage_age_days"], item["name"].casefold(), item["document_id"])
