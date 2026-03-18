from django.urls import path
from . import views

urlpatterns = [
    path('get_excel_columns/', views.get_excel_columns, name='get_excel_columns'),
    path('compare/', views.compare, name='compare'),
    path('create_queue/', views.create_queue, name='create_queue'),
    path('excel_to_cover_pages_stream/<uuid:uuid>/', views.excel_to_cover_pages_stream, name='excel_to_cover_pages_stream'),
    path('test/', views.test, name='test'),
]