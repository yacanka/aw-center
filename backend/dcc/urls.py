from django.urls import path

from .issue_draft_views import (
    issue_draft_approve,
    issue_draft_create,
    issue_draft_detail,
    issue_draft_preflight,
    issue_draft_publish,
)
from .job_views import confirm_dcc_document_job, preview_dcc_document_job
from .views import DccRecordCollectionView, DccRecordDetailView

urlpatterns = [
    path("records/", DccRecordCollectionView.as_view(), name="dcc-records"),
    path(
        "records/<uuid:record_id>/",
        DccRecordDetailView.as_view(),
        name="dcc-record-detail",
    ),
    path(
        "jobs/create-document/preview/",
        preview_dcc_document_job,
        name="preview_dcc_document_job",
    ),
    path(
        "jobs/create-document/<uuid:job_id>/confirm/",
        confirm_dcc_document_job,
        name="confirm_dcc_document_job",
    ),
    path("issue-drafts/", issue_draft_create, name="issue_draft_create"),
    path("issue-drafts/<uuid:draft_id>/", issue_draft_detail, name="issue_draft_detail"),
    path(
        "issue-drafts/<uuid:draft_id>/approve/",
        issue_draft_approve,
        name="issue_draft_approve",
    ),
    path(
        "issue-drafts/<uuid:draft_id>/preflight/",
        issue_draft_preflight,
        name="issue_draft_preflight",
    ),
    path(
        "issue-drafts/<uuid:draft_id>/publish/",
        issue_draft_publish,
        name="issue_draft_publish",
    ),
]
