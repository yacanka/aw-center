"""Explain DCC preview readiness without exposing captured source content."""

from .document_snapshot import DccSnapshotError

MAX_ACKNOWLEDGEMENTS = 16


def assess_dcc_readiness(snapshot, missing_fields):
    """Return a deterministic score and content-free readiness checklist."""

    checks = [template_check(), source_field_check(missing_fields), panel_check(snapshot)]
    warnings = [check["code"] for check in checks if check["status"] == "warning"]
    return {
        "readiness_score": readiness_score(checks),
        "readiness_level": "review" if warnings else "ready",
        "readiness_checks": [public_check(check) for check in checks],
        "readiness_warning_codes": warnings,
        "requires_readiness_acknowledgement": bool(warnings),
        "warning_count": len(warnings),
    }


def validate_readiness_acknowledgement(summary, payload):
    """Require the client to acknowledge every current readiness warning."""

    expected = normalized_codes(summary.get("readiness_warning_codes", []))
    if not expected:
        return []
    if not hasattr(payload, "get"):
        raise invalid_acknowledgement()
    received = normalized_codes(payload.get("acknowledged_warning_codes", []))
    if received != expected:
        raise DccSnapshotError(
            "Review and acknowledge every DCC readiness warning before confirmation.",
            "DCC_READINESS_ACK_REQUIRED",
            409,
        )
    return expected


def normalized_codes(values):
    """Return a bounded, unique warning-code list or reject malformed input."""

    if not isinstance(values, list) or len(values) > MAX_ACKNOWLEDGEMENTS:
        raise invalid_acknowledgement()
    normalized = sorted({str(value).strip() for value in values if str(value).strip()})
    if any(len(value) > 64 for value in normalized):
        raise invalid_acknowledgement()
    return normalized


def invalid_acknowledgement():
    """Return the stable validation error for malformed acknowledgement data."""

    return DccSnapshotError(
        "DCC readiness acknowledgement is invalid.", "DCC_READINESS_ACK_INVALID", 400
    )


def template_check():
    """Describe the already-proven dry-render invariant."""

    return check(
        "DCC_TEMPLATE_READY", "Template rendering", "success",
        "The registered template rendered the immutable snapshot successfully.",
        "No action is required.", 30, 30,
    )


def source_field_check(missing_fields):
    """Score safe recommended-field coverage without returning captured values."""

    total = 5
    present = total - len(missing_fields)
    if not missing_fields:
        return check(
            "DCC_SOURCE_FIELDS", "Recommended JIRA fields", "success",
            "All recommended source fields are populated.", "No action is required.", 30, 30,
        )
    detail = f"{present} of {total} recommended source fields are populated."
    hint = f"Update or explicitly accept these omissions: {', '.join(missing_fields)}."
    return check("DCC_SOURCE_FIELDS", "Recommended JIRA fields", "warning", detail, hint, present * 6, 30)


def panel_check(snapshot):
    """Make zero-panel generation an explicit human-reviewed decision."""

    count = max(0, int(snapshot.get("panel_count") or 0))
    if count:
        return check(
            "DCC_PANEL_COVERAGE", "Panel coverage", "success",
            f"{count} panel subtasks are captured.", "No action is required.", 15, 15,
        )
    return check(
        "DCC_PANEL_COVERAGE", "Panel coverage", "warning",
        "No panel subtasks are captured.",
        "Confirm that a parent-only DCC is intentional or add panel subtasks in JIRA.", 0, 15,
    )


def readiness_score(checks):
    """Normalize applicable weighted checks to a stable 0-100 score."""

    earned = sum(item["earned"] for item in checks)
    maximum = sum(item["maximum"] for item in checks)
    return round(earned * 100 / maximum) if maximum else 100


def public_check(item):
    """Remove internal scoring weights from the API checklist."""

    return {key: value for key, value in item.items() if key not in {"earned", "maximum"}}


def check(code, title, status, detail, recovery_hint, earned, maximum):
    """Build one bounded readiness check."""

    return {
        "code": code, "title": title, "status": status, "detail": detail,
        "recovery_hint": recovery_hint, "earned": earned, "maximum": maximum,
    }
