from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('dcc/', include('projects.havasoj.dcc.urls')),
    path('compdocs/', include('projects.havasoj.compdocs.urls')),
    path('orgs/', include('projects.havasoj.orgs.urls')),
]