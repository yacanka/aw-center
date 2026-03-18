from django.urls import path, include
from .views import split_pdf_zip, compare_pdf

urlpatterns = [
    path('split_pdf_zip/', split_pdf_zip, name="split_pdf_zip"),
    path('compare/', compare_pdf, name="compare"),
]