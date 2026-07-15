from django.urls import path
from . import api_views, views

urlpatterns = [
    path('script/', views.create_script, name='script'),
    path('run_dxl/', views.run_dxl, name='run_dxl'),
    path('test/', views.test, name='test'),
    path('status/', api_views.status_view, name='doors_status'),
    path('modules/check/', api_views.check_module, name='doors_check_module'),
    path('objects/', api_views.list_objects, name='doors_list_objects'),
    path('objects/detail/', api_views.get_object, name='doors_get_object'),
    path('objects/update/', api_views.update_object, name='doors_update_object'),
    path('objects/create/', api_views.create_object, name='doors_create_object'),
]
