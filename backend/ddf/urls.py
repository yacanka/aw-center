from django.urls import path
from . import views
urlpatterns = [
    path('', views.DDFView.as_view(), name="ddf"),
    path('<int:pk>/', views.DDFObjView.as_view(), name='ddf_obj'),
    path('upload/', views.upload_ddf, name='upload'),
    path('assessment/', views.ddf_assessment, name='assessment'),
]