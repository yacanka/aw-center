from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('dcc/', include('projects.ozgur.dcc.urls')),
    path('compdocs/', include('projects.ozgur.compdocs.urls')),
    path('orgs/', include('projects.ozgur.orgs.urls')),
]