"""Request-time access decisions using existing domain and menu policies."""
from dataclasses import replace

from orgs.access_policy import authorized_project_ids
from orgs.models import Project
from projects.registry import get_project_definitions_by_capability

from .catalog import GuideEntry, load_guides


def _domain_projects(user, domain):
    slugs = [entry.slug for entry in get_project_definitions_by_capability(domain)]
    return tuple(Project.objects.filter(
        pk__in=authorized_project_ids(user, domain, "viewer"), slug__in=slugs,
    ).order_by("slug"))


def authorized_guides(user) -> tuple[GuideEntry, ...]:
    """Return fresh enabled/capability/role-filtered guides; history grants no access."""
    if not user or not user.is_authenticated or not user.is_active:
        return ()
    compliance_projects = _domain_projects(user, "compliance")
    has_dcc = bool(_domain_projects(user, "dcc"))
    has_organization = bool(_domain_projects(user, "organization"))
    entries = []
    for entry in load_guides():
        if entry.path.startswith("/compdocs/") and not compliance_projects:
            continue
        if entry.path == "/jira" and not has_dcc:
            continue
        if entry.path == "/organization" and not has_organization:
            continue
        if not _menu_access(user, entry.path):
            continue
        entries.append(entry)
    template = next((entry for entry in entries if entry.id == "compliance-home"), None)
    if template:
        for project in compliance_projects:
            entries.append(replace(
                template, id=f"compliance-project-{project.slug}",
                title=f"Compliance Docs — {project.name}", path=f"/compdocs/{project.slug}",
                purpose="Browse and manage the selected project's compliance document register.",
                inputs=("Selected project and document filters.",),
                outputs=("Filtered register, document details and permitted exports.",),
                steps=("Open the project register.", "Filter documents and open details.",
                       "Use the available import, edit, review or export controls according to your role."),
                limitations=("Viewer roles are read-only. Changes require the relevant project role.",
                             "The assistant does not read or modify live documents."),
                keywords=(project.slug, project.name, "compliance", "documents", "uyumluluk"),
            ))
    return tuple(sorted(entries, key=lambda entry: entry.id))


def _menu_access(user, path):
    if user.is_superuser:
        return True
    if path == "/developer/test-data":
        return False
    if path == "/developer/doors":
        return user.is_staff
    if path == "/users":
        return user.is_staff and any(user.has_perm(name) for name in ("auth.view_user", "auth.add_user"))
    if path == "/ddfAssistant":
        return any(user.has_perm(name) for name in ("ddf.view_ddf", "ddf.add_ddf"))
    return True
