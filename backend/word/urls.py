from django.urls import path
from . import views
from .job_views import create_analysis_job, create_translation_job

urlpatterns = [
    path('compare/', views.compare, name='compare'),
    path('jobs/analyze/', create_analysis_job, name='word_analysis_job_create'),
    path('jobs/translate/', create_translation_job, name='word_translation_job_create'),
]
