from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('dcc/', include('projects.aesa.dcc.urls')),
    path('compdocs/', include('projects.aesa.compdocs.urls')),
    path('orgs/', include('projects.aesa.orgs.urls')),
]