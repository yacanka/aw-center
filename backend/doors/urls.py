from django.urls import path
from . import views

urlpatterns = [
    path('script/', views.create_script, name='script'),
    path('run_dxl/', views.run_dxl, name='run_dxl'),
    path('test/', views.test, name='test'),
]