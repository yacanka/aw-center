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
    """Protect collection upserts and destructive deletion with combined rights."""

    perms_map = {
        **StrictDjangoModelPermissions.perms_map,
        "POST": [
            "%(app_label)s.add_%(model_name)s",
            "%(app_label)s.change_%(model_name)s",
        ],
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
