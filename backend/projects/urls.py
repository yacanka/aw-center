"""API routes for project registry metadata."""

from django.urls import path

from common.compdoc_import_api import (
    CompDocImportAuditCollectionView,
    CompDocImportAuditDetailView,
)

from .api import project_registry

urlpatterns = [
    path("registry/", project_registry, name="projects_registry"),
    path(
        "import-audits/",
        CompDocImportAuditCollectionView.as_view(),
        name="compdoc-import-audits",
    ),
    path(
        "import-audits/<uuid:audit_id>/",
        CompDocImportAuditDetailView.as_view(),
        name="compdoc-import-audit-detail",
    ),
]
