"""Deterministic parameter contracts for DCC document jobs."""


def build_preview_parameters(issue_key):
    """Return idempotency parameters without transient credentials."""

    return {
        "issue_key": issue_key,
        "snapshot_schema": 1,
        "confirmation_required": True,
    }
