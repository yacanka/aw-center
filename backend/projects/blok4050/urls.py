from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('dcc/', include('projects.blok4050.dcc.urls')),
    path('compdocs/', include('projects.blok4050.compdocs.urls')),
    path('orgs/', include('projects.blok4050.orgs.urls')),
]