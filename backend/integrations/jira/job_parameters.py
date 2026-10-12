"""Deterministic parameter contracts for DCC document jobs."""


def build_preview_parameters(issue_key, project_ids):
    """Return idempotency parameters without transient credentials."""

    return {
        "issue_key": issue_key,
        "project_ids": [int(project_id) for project_id in project_ids],
        "snapshot_schema": 1,
        "confirmation_required": True,
    }
