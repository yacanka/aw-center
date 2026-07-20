from django.urls import path
from . import views
from .issue_draft_views import (
    issue_draft_approve, issue_draft_create, issue_draft_detail, issue_draft_preflight,
    issue_draft_publish,
)
from .job_views import confirm_dcc_document_job, preview_dcc_document_job
from .compdoc_traceability_views import compdoc_traceability_list
from .compdoc_refresh_views import refresh_compdoc_trace_preview
from .compdoc_recommendation_views import apply_compdoc_recommendations

urlpatterns = [
    path(
        'compdoc-traceability/', compdoc_traceability_list,
        name='compdoc_traceability_list',
    ),
    path(
        'compdoc-traceability/<uuid:trace_id>/refresh-preview/',
        refresh_compdoc_trace_preview,
        name='refresh_compdoc_trace_preview',
    ),
    path(
        'jobs/create-document/preview/', preview_dcc_document_job,
        name='preview_dcc_document_job',
    ),
    path(
        'jobs/create-document/<uuid:job_id>/confirm/', confirm_dcc_document_job,
        name='confirm_dcc_document_job',
    ),
    path(
        'jobs/create-document/<uuid:job_id>/compdoc-recommendations/',
        apply_compdoc_recommendations,
        name='apply_compdoc_recommendations',
    ),
    path('issue-drafts/', issue_draft_create, name='issue_draft_create'),
    path('issue-drafts/<uuid:draft_id>/', issue_draft_detail, name='issue_draft_detail'),
    path(
        'issue-drafts/<uuid:draft_id>/approve/', issue_draft_approve,
        name='issue_draft_approve',
    ),
    path(
        'issue-drafts/<uuid:draft_id>/preflight/', issue_draft_preflight,
        name='issue_draft_preflight',
    ),
    path(
        'issue-drafts/<uuid:draft_id>/publish/', issue_draft_publish,
        name='issue_draft_publish',
    ),
    path('api/', views.JIRA_DCC_ViewSet.as_view(), name='api'),
    path('api/<int:pk>/', views.JIRA_DCC_ViewSet.as_view(), name='api'),
    path('issues/', views.get_issue_list, name='issues'),
    path('add/', views.add_new_dcc, name='add'),
    path('get_issue/', views.get_issue, name='get_issue'),
    path('create_issue/', views.create_issue, name='create_issue'),
    path('send_mail/', views.send_mail, name='send_mail'),
    path('upload/', views.upload_ecd, name='upload'),
    path('ecd_assessment/', views.ecd_assessment, name='ecd_assessment'),
    path('create_subtask_stream/<uuid:uuid>/', views.create_subtask_stream, name='create_subtask_stream'),
    path('create_subtask_excel_stream/<uuid:uuid>/', views.create_subtask_excel_stream, name='create_subtask_excel_stream'),
    path('create_queue/', views.create_queue, name='create_queue'),
    path('subtask_fields/', views.get_subtask_fields, name='subtask_fields'),
    path('check_session/', views.check_session, name='check_session'),
    path('add_attachment/', views.add_attachment, name='add_attachment'),
]
