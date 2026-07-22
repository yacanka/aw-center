from django.urls import path
from . import views
from .custom_check_views import custom_check_collection, custom_check_detail
from .job_views import create_analysis_job, create_translation_job

urlpatterns = [
    path('compare/', views.compare, name='compare'),
    path('analysis-checks/', custom_check_collection, name='word_analysis_checks'),
    path(
        'analysis-checks/<uuid:check_id>/',
        custom_check_detail,
        name='word_analysis_check_detail',
    ),
    path('jobs/analyze/', create_analysis_job, name='word_analysis_job_create'),
    path('jobs/translate/', create_translation_job, name='word_translation_job_create'),
]
