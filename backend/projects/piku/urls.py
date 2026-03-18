from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('dcc/', include('projects.piku.dcc.urls')),
    path('compdocs/', include('projects.piku.compdocs.urls')),
    path('orgs/', include('projects.piku.orgs.urls')),
]