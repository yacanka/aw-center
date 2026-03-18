from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('dcc/', include('projects.hys.dcc.urls')),
    path('compdocs/', include('projects.hys.compdocs.urls')),
    path('orgs/', include('projects.hys.orgs.urls')),
]