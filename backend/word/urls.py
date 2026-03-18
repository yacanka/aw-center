from django.urls import path
from . import views

urlpatterns = [
    path('compare/', views.compare, name='compare'),
    path('create_queue/', views.create_queue, name='create_queue'),
    path('translate/<uuid:uuid>/', views.translate, name='translate'),
]