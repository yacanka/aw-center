"""Permission-aware stale CompDoc-to-DCC attention signals."""

from django.apps import apps
from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber

from dcc.compdoc_changes import compare_captured_compdoc
from dcc.compdoc_capture import captured_model_field_names
from dcc.compdoc_versions import recent_current_versions
from dcc.models import DccCompdocTrace
from projects.registry import get_project_definitions_by_capability

MAX_CHANGED_PER_PROJECT = 24
MAX_STALE_ITEMS = 6


def stale_compdoc_trace_items(user, boundary):
    """Return recent source changes whose newest confirmed DCC uses an older version."""

    project_models = authorized_project_models(user)
    project_slugs = [project.slug for project, _model in project_models]
    if not project_slugs or not DccCompdocTrace.objects.filter(
        project_slug__in=project_slugs
    ).exists():
        return []
    versions = collect_recent_versions(project_models, boundary)
    traces = latest_traces(versions)
    changes = load_source_changes(versions, traces)
    items = [
        build_item(version, traces.get(version_key(version)), changes)
        for version in versions
    ]
    stale_items = [item for item in items if item]
    return sorted(stale_items, key=lambda item: item["_sort_at"], reverse=True)[:MAX_STALE_ITEMS]


def authorized_project_models(user):
    """Resolve only enabled CompDoc models visible with the DCC read permission."""

    if not user.has_perm("dcc.view_jira_dcc"):
        return []
    authorized = []
    for project in get_project_definitions_by_capability("compdocs"):
        model = apps.get_model(project.slug, "CompDoc")
        if model and user.has_perm(f"{project.slug}.view_compdoc"):
            authorized.append((project, model))
    return authorized


def collect_recent_versions(project_models, boundary):
    """Load current recent history rows in one bounded query per authorized project."""

    versions = []
    for project, model in project_models:
        rows = recent_current_versions(model, project.slug, boundary, MAX_CHANGED_PER_PROJECT)
        versions.extend(
            {
                "id": row.id,
                "history_id": row.history_id,
                "history_date": row.history_date,
                "name": row.name,
                "document": row,
                "model": model,
                "project": project,
            }
            for row in rows
        )
    return versions


def latest_traces(versions):
    """Load the newest confirmed trace for every candidate source in one query."""

    filters = Q()
    for version in versions:
        filters |= Q(project_slug=version["project"].slug, compdoc_id=version["id"])
    if not filters:
        return {}
    traces = DccCompdocTrace.objects.filter(filters).annotate(
        source_rank=Window(
            expression=RowNumber(),
            partition_by=[F("project_slug"), F("compdoc_id")],
            order_by=[F("confirmed_at").desc(), F("id").desc()],
        )
    ).filter(source_rank=1)
    return {(trace.project_slug, trace.compdoc_id): trace for trace in traces}


def load_source_changes(versions, traces):
    """Bulk-compare every stale trace with its project's current history row."""

    changes = {}
    for project_slug in sorted({version["project"].slug for version in versions}):
        project_versions = [
            version for version in versions if version["project"].slug == project_slug
        ]
        changes.update(project_source_changes(project_versions, traces))
    return changes


def project_source_changes(versions, traces):
    """Load one project's captured history rows and return value-free comparisons."""

    relevant = [
        (version, traces.get(version_key(version))) for version in versions
    ]
    relevant = [pair for pair in relevant if is_stale_pair(*pair)]
    if not relevant:
        return {}
    model = versions[0]["model"]
    source_ids = {
        trace.source_history_id
        for _version, trace in relevant
        if trace.source_history_id
    }
    history = model.history.model.objects.filter(history_id__in=source_ids).only(
        "id", "history_id", *captured_model_field_names(model)
    )
    sources = {(row.id, row.history_id): row for row in history}
    return {
        trace.id: compare_captured_compdoc(
            version["document"], sources.get((version["id"], trace.source_history_id))
        )
        for version, trace in relevant
    }


def is_stale_pair(version, trace):
    """Return whether one newest trace references an older source version."""

    return bool(trace and trace.source_history_id != version["history_id"])


def build_item(version, trace, changes):
    """Convert one stale source version into a content-minimized attention item."""

    if not trace or trace.source_history_id == version["history_id"]:
        return None
    source_change = changes.get(trace.id)
    if source_change and source_change["comparison_status"] == "unchanged":
        return None
    project = version["project"]
    occurred_at = version["history_date"]
    identifier = f"compdoc-trace:{trace.id}:{version['history_id']}"
    return {
        "id": identifier,
        "kind": "compdoc_trace",
        "severity": "warning",
        "title": f"CompDoc changed after DCC: {version['name']}",
        "detail": change_detail(trace, project, source_change),
        "guidance": change_guidance(source_change),
        "action_label": "Review source and DCC history",
        "action_path": f"/compdocs/{project.slug}?compdoc={version['id']}&dcc_trace={trace.id}",
        "occurred_at": occurred_at,
        "_sort_at": occurred_at,
    }


def change_detail(trace, project, source_change):
    """Explain affected DCC fields without returning their old or current values."""

    prefix = f"{trace.issue_key} uses an older {project.display_name} source version."
    if not source_change or source_change["comparison_status"] == "unavailable":
        return f"{prefix} Field comparison is unavailable."
    labels = ", ".join(field["label"] for field in source_change["changed_fields"])
    return f"{prefix} Changed DCC fields: {labels}."


def change_guidance(source_change):
    """Return a deterministic review instruction for the comparison state."""

    if not source_change or source_change["comparison_status"] == "unavailable":
        return "Review the source manually because its captured history is unavailable."
    return "Review the listed fields and regenerate the DCC if its approved output is affected."


def version_key(version):
    """Return the generic project and source key used by persisted trace rows."""

    return version["project"].slug, version["id"]
