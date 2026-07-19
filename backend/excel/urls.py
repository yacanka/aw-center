from django.urls import path
from . import views
from .job_views import create_cover_page_job

urlpatterns = [
    path('get_excel_columns/', views.get_excel_columns, name='get_excel_columns'),
    path('compare/', views.compare, name='compare'),
    path('jobs/cover-pages/', create_cover_page_job, name='cover_page_job_create'),
]
