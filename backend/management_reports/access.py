"""Registry allowlist and current project read authorization."""
from django.apps import apps
from rest_framework.exceptions import PermissionDenied, ValidationError

from projects.registry import get_project_definitions_by_capability


def project_options(user):
    return [
        {"slug": definition.slug, "display_name": definition.display_name}
        for definition in get_project_definitions_by_capability("compdocs")
        if can_view_project(user, definition)
    ]


def project_model(definition):
    return apps.get_app_config(definition.app_label.rsplit(".", 1)[-1]).get_model("CompDoc")


def can_view_project(user, definition):
    model = project_model(definition)
    return user.has_perm(f"{model._meta.app_label}.view_compdoc")


def authorized_projects(user, slugs):
    """Reject unknown scopes before model lookup, then require every permission."""
    definitions = {item.slug: item for item in get_project_definitions_by_capability("compdocs")}
    if not slugs or len(slugs) > len(definitions) or len(set(slugs)) != len(slugs):
        raise ValidationError({"project_slugs": "Choose a nonempty, unique enabled project scope."})
    if any(slug not in definitions for slug in slugs):
        raise ValidationError({"project_slugs": "Unknown or disabled reporting project."})
    selected = [definitions[slug] for slug in sorted(slugs)]
    if not all(can_view_project(user, item) for item in selected):
        raise PermissionDenied("Project view permission is required for every selected project.")
    return selected
