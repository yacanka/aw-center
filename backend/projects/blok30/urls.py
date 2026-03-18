from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('dcc/', include('projects.blok30.dcc.urls')),
    path('compdocs/', include('projects.blok30.compdocs.urls')),
    path('orgs/', include('projects.blok30.orgs.urls')),
]