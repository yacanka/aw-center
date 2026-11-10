from django.urls import path
from . import views

urlpatterns = [
    path('presets/', views.presets, name='comparison_presets'),
    path('inspections/', views.create_inspection, name='comparison_inspect'),
    path('inspections/<uuid:job_id>/', views.inspection_detail, name='comparison_inspection_detail'),
    path('jobs/', views.create_comparison, name='comparison_create'),
]
