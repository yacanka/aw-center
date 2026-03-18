from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('dcc/', include('projects.gokbey.dcc.urls')),
    path('compdocs/', include('projects.gokbey.compdocs.urls')),
    path('orgs/', include('projects.gokbey.orgs.urls')),
]