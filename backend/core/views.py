from django.shortcuts import render, redirect
from django.http import HttpResponse

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated

def index(request):
    return render(request, "index.html")

