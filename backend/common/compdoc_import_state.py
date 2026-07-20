"""Database-state proof for confirmed CompDoc import plans."""

import hashlib
import json

from rest_framework import status
from rest_framework.exceptions import APIException


class CompDocImportDatabaseConflict(APIException):
    """Reject an import whose reviewed target records changed before confirmation."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "COMPDOC_IMPORT_DATABASE_CONFLICT"
    default_detail = "Compliance documents changed after this import preview."


def import_plan_fingerprint(plan):
    """Return a canonical digest of every database target represented by a plan."""

    encoded = json.dumps(
        import_plan_state(plan),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def import_plan_state(plan):
    """Return deterministic business-key, identity, history, and action evidence."""

    state = [row_state(row) for row in plan.rows]
    return sorted(state, key=lambda item: item["cover_page_no"].casefold())


def row_state(row):
    """Return one content-free database-state entry for a planned workbook row."""

    instance = row.instance
    return {
        "cover_page_no": str(row.payload.get("cover_page_no") or ""),
        "instance_id": str(instance.pk) if instance else "",
        "source_history_id": row.source_history_id,
        "action": row.action,
    }


def require_matching_import_state(plan, expected_fingerprint):
    """Reject a plan when its locked database state differs from the signed preview."""

    if import_plan_fingerprint(plan) != expected_fingerprint:
        raise CompDocImportDatabaseConflict()
