"""Independent target, release-age and metadata signals for risk policy v2."""

from datetime import timedelta

from dateutil.relativedelta import relativedelta


def build_risk_signals(document, today):
    """Score canonical fields; workflow history remains informational only."""
    target = document.get("revised_target_date") or document.get("target_date")
    raw_status = str(document.get("status") or "").strip()
    signals = [
        _target_signal(target, document.get("release_date"), today),
        _review_signal(raw_status, document.get("release_date"), today),
        *_missing_signals(document, target, raw_status),
    ]
    return [signal for signal in signals if signal]


def stage_age_days(entries, today):
    """Return non-negative age of the latest valid workflow stage."""
    dated_entries = [entry_date for _status, entry_date in entries if entry_date]
    return max(0, (today - dated_entries[-1]).days) if dated_entries else 0


def _target_signal(target, release, today):
    if not target or release:
        return None
    if target < today:
        severe = target + relativedelta(months=3) <= today
        overdue_days = (today - target).days
        return _signal(
            "target_overdue", "Target overdue", 100 if severe else 80,
            overdue_days, (target + relativedelta(months=3) - target).days if severe else 0,
            f"Unreleased document is {overdue_days} days past its current target.",
        )
    if target < today + relativedelta(months=1):
        days_left = (target - today).days
        return _signal(
            "target_approaching", "Target approaching", 30, days_left,
            (today + relativedelta(months=1) - today).days,
            f"Unreleased document reaches its current target in {days_left} days.",
        )
    return None


def _review_signal(status, release, today):
    if not release or release > today:
        return None
    if status == "authority_review":
        thresholds = [(release + relativedelta(months=2), 30),
                      (release + relativedelta(months=1), 20)]
        label = "Authority review aging"
    elif status == "airworthiness_review":
        thresholds = [(release + relativedelta(months=1), 30),
                      (release + timedelta(days=15), 20)]
        label = "Aw Review aging"
    else:
        return None
    for threshold, points in thresholds:
        if today >= threshold:
            age = (today - release).days
            return _signal(
                "review_aging", label, points, age, (threshold - release).days,
                f"{label}: {age} days since release; only the highest age tier applies.",
            )
    return None


def _missing_signals(document, target, status):
    fields = [
        ("target_date", "current target date", not target),
        ("status", "status", not status or status == "unknown"),
        ("cover_page", "cover page number", _blank(document.get("cover_page_no"))),
        ("panel", "panel", _blank(document.get("panel"))),
        ("ata", "ATA", _blank(document.get("ata"))),
    ]
    return [
        _signal(f"missing_{key}", f"Missing {label}", 20, 1, 0,
                f"No {label} is registered.", unit="missing")
        for key, label, missing in fields if missing
    ]


def _blank(value):
    return not str(value or "").strip()


def _signal(code, label, points, observed, threshold, detail, unit="days"):
    return {
        "code": code, "label": label, "points": points,
        "severity": "high" if points >= 25 else "medium" if points >= 15 else "low",
        "observed": observed, "threshold": threshold, "unit": unit, "detail": detail,
    }
