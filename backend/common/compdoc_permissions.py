"""Deny-by-default model permissions for project compliance documents."""

from rest_framework.permissions import DjangoModelPermissions


class StrictDjangoModelPermissions(DjangoModelPermissions):
    """Require Django's view permission for safe read requests too."""

    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }


class CompDocCollectionPermissions(StrictDjangoModelPermissions):
    """Allow explicit creation while keeping destructive actions protected."""

    perms_map = {
        **StrictDjangoModelPermissions.perms_map,
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "DELETE": [
            "%(app_label)s.view_%(model_name)s",
            "%(app_label)s.delete_%(model_name)s",
        ],
    }


class CompDocImportPermissions(StrictDjangoModelPermissions):
    """Require create and update rights because imports perform upserts."""

    perms_map = {
        **StrictDjangoModelPermissions.perms_map,
        "POST": [
            "%(app_label)s.add_%(model_name)s",
            "%(app_label)s.change_%(model_name)s",
        ],
    }


class CompDocChangePermissions(StrictDjangoModelPermissions):
    """Map action-style POST requests to the concrete model change permission."""

    perms_map = {
        **StrictDjangoModelPermissions.perms_map,
        "POST": ["%(app_label)s.change_%(model_name)s"],
    }


class CompDocArchivePermissions(StrictDjangoModelPermissions):
    """Map archive POST requests to the project's delete permission."""

    perms_map = {
        **StrictDjangoModelPermissions.perms_map,
        "POST": ["%(app_label)s.delete_%(model_name)s"],
    }


class CompDocRestorePermissions(StrictDjangoModelPermissions):
    """Require both change and delete rights before restoring evidence."""

    perms_map = {
        **StrictDjangoModelPermissions.perms_map,
        "POST": [
            "%(app_label)s.change_%(model_name)s",
            "%(app_label)s.delete_%(model_name)s",
        ],
    }


class CompDocActionViewPermissions(StrictDjangoModelPermissions):
    """Require project view permission for read-like action requests."""

    perms_map = {
        **StrictDjangoModelPermissions.perms_map,
        "POST": ["%(app_label)s.view_%(model_name)s"],
    }


class CompDocAssigneePermissions(StrictDjangoModelPermissions):
    """Restrict assignment directory reads to project editors."""

    perms_map = {
        **StrictDjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.change_%(model_name)s"],
        "HEAD": ["%(app_label)s.change_%(model_name)s"],
    }


class CompDocExportPermissions(StrictDjangoModelPermissions):
    """Treat selected-export POST as a project read operation."""

    perms_map = {
        **StrictDjangoModelPermissions.perms_map,
        "POST": ["%(app_label)s.view_%(model_name)s"],
    }


class WorkflowManagerOverride:
    """Allow the explicit cross-project workflow administrator permission."""

    def has_permission(self, request, view):
        if request.user.is_authenticated and request.user.has_perm(
            "common.manage_compdoc_workflow"
        ):
            return True
        return super().has_permission(request, view)


class CompDocReviewChangePermissions(WorkflowManagerOverride, CompDocChangePermissions):
    """Allow project editors or exceptional workflow administrators."""


class CompDocReviewActionPermissions(WorkflowManagerOverride, CompDocActionViewPermissions):
    """Allow project viewers or exceptional workflow administrators."""


class CompDocReviewAssigneePermissions(WorkflowManagerOverride, CompDocAssigneePermissions):
    """Allow assignee lookup for project editors or workflow administrators."""
