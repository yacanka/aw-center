from django.urls import path
from . import api_views, views

urlpatterns = [
    path('script/', views.create_script, name='script'),
    path('status/', api_views.status_view, name='doors_status'),
    path('module-check-jobs/', api_views.create_module_check_job, name='doors_module_check_job'),
    path('object-list-jobs/', api_views.create_object_list_job, name='doors_object_list_job'),
    path('module-export-jobs/', api_views.create_module_export_job, name='doors_module_export_job'),
    path('object-detail-jobs/', api_views.create_object_detail_job, name='doors_object_detail_job'),
    path(
        'discipline-check-jobs/',
        api_views.create_discipline_check_job,
        name='doors_discipline_check_job',
    ),
    path('object-update-jobs/', api_views.create_object_update_job, name='doors_object_update_job'),
    path('object-create-jobs/', api_views.create_object_create_job, name='doors_object_create_job'),
    path(
        'requirement-link-jobs/',
        api_views.create_requirement_link_job,
        name='doors_requirement_link_job',
    ),
]
