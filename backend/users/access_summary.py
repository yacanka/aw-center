"""Read-only project authorization summaries for the user administration API."""

from orgs.access_policy import role_rank


def project_access_summary(user):
    """Combine direct and inherited assignments using the canonical role order.

    UserView prefetches both assignment paths so directory serialization does
    not issue queries per user, project or group. Disabled projects remain
    visible for auditing; their assignments do not imply usable access.
    """
    entries = {}
    assignments = [(assignment, None) for assignment in user.project_role_assignments.all()]
    for group in user.groups.all():
        assignments.extend((assignment, group) for assignment in group.project_role_assignments.all())
    for assignment, group in assignments:
        project = assignment.project
        key = (project.pk, assignment.domain)
        entry = entries.setdefault(key, {
            "project_id": project.pk,
            "project_name": project.name,
            "project_slug": project.slug,
            "project_enabled": project.enabled,
            "domain": assignment.domain,
            "application": assignment.get_domain_display(),
            "role": assignment.role,
            "sources": [],
        })
        if role_rank(assignment.domain, assignment.role) > role_rank(assignment.domain, entry["role"]):
            entry["role"] = assignment.role
        entry["sources"].append({
            "kind": "group" if group else "direct",
            "group_id": group.pk if group else None,
            "group_name": group.name if group else None,
            "role": assignment.role,
        })
    return sorted(entries.values(), key=lambda entry: (entry["project_name"], entry["project_id"], entry["domain"]))
