"""Individual explainable signals used by the CompDoc risk engine."""


ACTIVE_WAIT_STATUSES = {
    "airworthiness_review",
    "to_be_re-submitted",
    "to_be_updated",
}


def build_risk_signals(document, entries, status, stage_age, today, policy):
    """Return every applicable risk reason for one compliance document."""

    signals = (
        _target_overdue_signal(entries, status, today),
        _long_wait_signal(status, stage_age, policy),
        _resubmission_signal(entries),
        _missing_reference_signal(document),
        _authority_aging_signal(status, stage_age, policy),
    )
    return [signal for signal in signals if signal]


def stage_age_days(entries, today):
    """Return non-negative age of the latest valid workflow stage."""

    dated_entries = [entry_date for _status, entry_date in entries if entry_date]
    return max(0, (today - dated_entries[-1]).days) if dated_entries else 0


def _target_overdue_signal(entries, status, today):
    target_date = entries[0][1] if entries else None
    overdue_days = (today - target_date).days if target_date and status == "delayed" else 0
    points = _scaled_points(overdue_days, 0, 15, 7, 5, 35)
    return _signal(
        "sla_target_overdue",
        "SLA target overdue",
        points,
        overdue_days,
        0,
        f"UBM target is {overdue_days} days overdue.",
    )


def _long_wait_signal(status, stage_age, policy):
    waited_days = stage_age if status in ACTIVE_WAIT_STATUSES else 0
    points = _scaled_points(waited_days, policy.long_wait_days, 8, 14, 4, 20)
    return _signal(
        "long_wait",
        "Long workflow wait",
        points,
        waited_days,
        policy.long_wait_days,
        f"Current workflow step has waited {waited_days} days.",
    )


def _resubmission_signal(entries):
    count = sum(status == "to_be_re-submitted" for status, _date in entries)
    points = min(24, count * 12)
    return _signal(
        "resubmission_cycle",
        "Re-submission cycle",
        points,
        count,
        0,
        f"Document entered re-submission {count} times.",
        unit="cycles",
    )


def _missing_reference_signal(document):
    values = [value for key, value in document.items() if key.startswith("tech_doc_no")]
    missing = not any(str(value or "").strip() for value in values)
    return _signal(
        "missing_technical_reference",
        "Missing technical reference",
        15 if missing else 0,
        1 if missing else 0,
        0,
        "No technical document number is registered.",
        unit="missing",
    )


def _authority_aging_signal(status, stage_age, policy):
    aging_days = stage_age if status == "authority_review" else 0
    points = _scaled_points(aging_days, policy.authority_aging_days, 14, 14, 4, 26)
    return _signal(
        "authority_aging",
        "Authority aging",
        points,
        aging_days,
        policy.authority_aging_days,
        f"Authority review has waited {aging_days} days.",
    )


def _signal(code, label, points, observed, threshold, detail, unit="days"):
    if not points:
        return None
    return {
        "code": code,
        "label": label,
        "points": points,
        "severity": "high" if points >= 25 else "medium" if points >= 15 else "low",
        "observed": observed,
        "threshold": threshold,
        "unit": unit,
        "detail": detail,
    }


def _scaled_points(value, threshold, base, step_days, step_points, maximum):
    if value <= threshold:
        return 0
    steps = (value - threshold - 1) // step_days
    return min(maximum, base + steps * step_points)
