"""Deterministic parameter contracts for DCC document jobs."""


def build_preview_parameters(issue_key, compdoc_project, compdoc_ids):
    """Return idempotency parameters without transient credentials."""

    return {
        "issue_key": issue_key,
        "snapshot_schema": 1,
        "confirmation_required": True,
        "compdoc_project": compdoc_project,
        "compdoc_ids": compdoc_ids,
    }
