from django.urls import path
from . import views

urlpatterns = [
    path('test/', views.Test, name='json_data'),
    path('api/', views.JIRA_DCC_ViewSet.as_view(), name='api'),
    path('api/<int:pk>/', views.JIRA_DCC_ViewSet.as_view(), name='api'),
    path('issues/', views.get_issue_list, name='issues'),
    path('add/', views.add_new_dcc, name='add'),
    path('get_issue/', views.get_issue, name='get_issue'),
    path('create_issue/', views.create_issue, name='create_issue'),
    path('send_mail/', views.send_mail, name='send_mail'),
    path('upload/', views.upload_ecd, name='upload'),
    path('ecd_assessment/', views.ecd_assessment, name='ecd_assessment'),
    path('sse_test/', views.sse_test, name='sse'),
    path('create_subtask_stream/<uuid:uuid>/', views.create_subtask_stream, name='create_subtask_stream'),
    path('create_subtask_excel_stream/<uuid:uuid>/', views.create_subtask_excel_stream, name='create_subtask_excel_stream'),
    path('create_dcc_stream/<uuid:uuid>/', views.create_dcc_stream, name='create_dcc_stream'),
    path('create_queue/', views.create_queue, name='create_queue'),
    path('check_session/', views.check_session, name='check_session'),
    path('add_attachment/', views.add_attachment, name='add_attachment'),
]